"""
Main Agent Orchestrator & ReAct Loop (`AgentOrchestrator`).

Coordinates:
- Multi-turn tool execution loop (up to `max_iterations`)
- Slash Command modes (`/plan`, `/grill-me`, `/boost`, `/teamwork`, `/compact`, `/schedule`, `/learn`)
- Human-in-the-loop (HITL) command approvals and `ask_question` interactive cards
- Subagent background execution and Reactive Wakeup delivery
- Real-time WebSocket event streaming to the Electron/React UI
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from engine.config import config_manager
from engine.core.prompts import build_system_prompt
from engine.core.scheduler import scheduler_manager
from engine.core.subagents import SubagentInstance, SubagentTypeSpec, subagent_manager
from engine.core.transcript import ConversationStore
from engine.llm.base import ToolCallRequest
from engine.llm.router import llm_router
from engine.skills.loader import discover_skills
from engine.tools.registry import execute_tool, get_builtin_tool_definitions
from engine.tools.terminal import terminal_manager

logger = logging.getLogger("micelio.core.agent")

SLASH_COMMAND_HINTS = {
    "/plan": "The user invoked `/plan`. Design a detailed step-by-step implementation plan in an artifact (`implementation_plan.md`) with `RequestFeedback=true` and stop for review before writing application code.",
    "/grill-me": "The user invoked `/grill-me`. Conduct a sharp, interactive architecture interview using `ask_question` to clarify edge cases and design tradeoffs before writing code.",
    "/boost": "The user invoked `/boost`. Apply deep architectural reasoning, verify edge cases, and validate all changes with automated tests.",
    "/teamwork": "The user invoked `/teamwork`. Decompose the project and launch parallel subagents (`invoke_subagent`) to research and implement components concurrently.",
    "/schedule": "The user invoked `/schedule`. Use the `schedule` tool to set up the requested timer or recurring cron job.",
    "/learn": "The user invoked `/learn`. Persist the learned workflow or corporate standard into a new or existing `SKILL.md` file inside the skills directory.",
}


class AgentOrchestrator:
    def __init__(self) -> None:
        self._event_listeners: List[Callable[[Dict[str, Any]], Any]] = []
        self._pending_questions: Dict[str, asyncio.Future] = {}
        self._pending_approvals: Dict[str, asyncio.Future] = {}

        # Wire background wakeup handlers
        subagent_manager.set_runner_callback(self._run_subagent_background)
        scheduler_manager.set_wakeup_handler(self._on_scheduler_wakeup)
        terminal_manager.register_wakeup_callback(self._on_terminal_wakeup)

    def add_event_listener(self, cb: Callable[[Dict[str, Any]], Any]) -> None:
        self._event_listeners.append(cb)

    def remove_event_listener(self, cb: Callable[[Dict[str, Any]], Any]) -> None:
        if cb in self._event_listeners:
            self._event_listeners.remove(cb)

    async def broadcast(self, event: Dict[str, Any]) -> None:
        for cb in list(self._event_listeners):
            try:
                res = cb(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def resolve_question(self, conversation_id: str, answers: Dict[str, Any]) -> bool:
        fut = self._pending_questions.pop(conversation_id, None)
        if fut and not fut.done():
            fut.set_result(answers)
            return True
        return False

    def resolve_approval(self, approval_id: str, approved: bool) -> bool:
        fut = self._pending_approvals.pop(approval_id, None)
        if fut and not fut.done():
            fut.set_result(approved)
            return True
        return False

    async def _wait_for_question(self, conversation_id: str, questions: List[Dict[str, Any]]) -> str:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending_questions[conversation_id] = fut
        await self.broadcast(
            {
                "type": "ask_question",
                "conversation_id": conversation_id,
                "questions": questions,
            }
        )
        answers = await fut
        lines = [f"- {k}: {v}" for k, v in (answers or {}).items()]
        return "\n".join(lines)

    async def _check_hitl_approval_if_needed(
        self,
        conversation_id: str,
        tc: ToolCallRequest,
    ) -> bool:
        sec = config_manager.config.security
        if tc.name != "run_command":
            return True

        cmd_line = str(tc.arguments.get("CommandLine", "")).strip()
        for prefix in sec.auto_approved_command_prefixes:
            if cmd_line.lower().startswith(prefix.lower()):
                return True

        is_destructive = any(
            tok in cmd_line.lower()
            for tok in ("rm -rf", "remove-item", "del /", "format ", "git push --force", "drop table")
        )
        if not sec.require_approval_for_commands and not (
            sec.require_approval_for_destructive_commands and is_destructive
        ):
            return True

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        approval_id = tc.id
        self._pending_approvals[approval_id] = fut
        await self.broadcast(
            {
                "type": "hitl_approval_request",
                "conversation_id": conversation_id,
                "approval_id": approval_id,
                "tool_name": tc.name,
                "command_line": cmd_line,
                "summary": tc.arguments.get("toolSummary", "Execute command"),
            }
        )
        return bool(await fut)

    async def handle_user_message(
        self,
        conversation_id: str,
        user_text: str,
        provider_override: Optional[str] = None,
        max_iterations: int = 15,
    ) -> None:
        store = ConversationStore(conversation_id)
        messages = store.load_messages()

        # Check for `/compact` slash command
        slash_hint = ""
        first_token = user_text.strip().split()[0].lower() if user_text.strip() else ""
        if first_token == "/compact":
            if len(messages) > 4:
                messages = messages[-4:]
                store.save_messages(messages)
            await self.broadcast(
                {
                    "type": "system_notice",
                    "conversation_id": conversation_id,
                    "message": "Contexto compactado (`/compact`). Se conservaron los turnos más recientes.",
                }
            )
            if user_text.strip().lower() == "/compact":
                return
        elif first_token in SLASH_COMMAND_HINTS:
            slash_hint = SLASH_COMMAND_HINTS[first_token]

        store.append_step(source="USER_EXPLICIT", step_type="USER_INPUT", content=user_text)
        messages.append({"role": "user", "content": user_text})
        store.save_messages(messages)

        await self._run_agent_loop(
            store=store,
            messages=messages,
            provider_override=provider_override,
            slash_hint=slash_hint,
            max_iterations=max_iterations,
        )

    async def _run_agent_loop(
        self,
        store: ConversationStore,
        messages: List[Dict[str, Any]],
        provider_override: Optional[str] = None,
        slash_hint: str = "",
        max_iterations: int = 15,
        include_write_tools: bool = True,
        include_subagent_tools: bool = True,
        include_mcp_tools: bool = True,
        custom_system_prompt: Optional[str] = None,
    ) -> str:
        conversation_id = store.conversation_id
        provider = llm_router.get_provider(provider_override)
        skills = discover_skills()
        subagents = subagent_manager.list_types()

        system_prompt = custom_system_prompt or build_system_prompt(
            conversation_id=conversation_id,
            artifact_dir=store.brain_dir,
            workspace_dir=config_manager.config.active_workspace,
            available_skills=skills,
            active_subagents=subagents,
            slash_command_hint=slash_hint,
        )

        tools = get_builtin_tool_definitions(
            include_write_tools=include_write_tools,
            include_subagent_tools=include_subagent_tools,
            include_mcp_tools=include_mcp_tools,
        )

        final_text = ""
        for _ in range(max_iterations):
            await self.broadcast(
                {
                    "type": "turn_start",
                    "conversation_id": conversation_id,
                    "provider": provider.provider_id,
                }
            )

            thinking_buf: List[str] = []
            text_buf: List[str] = []
            tool_calls: List[ToolCallRequest] = []

            try:
                async for chunk in provider.stream_chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    tools=tools,
                ):
                    if chunk.type == "thinking" and chunk.delta:
                        thinking_buf.append(chunk.delta)
                        await self.broadcast(
                            {
                                "type": "thinking_delta",
                                "conversation_id": conversation_id,
                                "delta": chunk.delta,
                            }
                        )
                    elif chunk.type == "text" and chunk.delta:
                        text_buf.append(chunk.delta)
                        await self.broadcast(
                            {
                                "type": "text_delta",
                                "conversation_id": conversation_id,
                                "delta": chunk.delta,
                            }
                        )
                    elif chunk.type == "tool_call" and chunk.tool_call:
                        tool_calls.append(chunk.tool_call)
                        await self.broadcast(
                            {
                                "type": "tool_call_start",
                                "conversation_id": conversation_id,
                                "tool_call": {
                                    "id": chunk.tool_call.id,
                                    "name": chunk.tool_call.name,
                                    "arguments": chunk.tool_call.arguments,
                                },
                            }
                        )
            except Exception as exc:
                err_msg = f"Error al invocar proveedor LLM (`{provider.provider_id}`): {exc}"
                logger.exception(err_msg)
                await self.broadcast(
                    {
                        "type": "error",
                        "conversation_id": conversation_id,
                        "message": err_msg,
                    }
                )
                return err_msg

            full_thinking = "".join(thinking_buf)
            full_text = "".join(text_buf)
            final_text = full_text

            serialized_tcs = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in tool_calls
            ]

            store.append_step(
                source="MODEL",
                step_type="PLANNER_RESPONSE",
                content=full_text,
                thinking=full_thinking,
                tool_calls=serialized_tcs if serialized_tcs else None,
            )

            messages.append(
                {
                    "role": "assistant",
                    "content": full_text,
                    "thinking": full_thinking,
                    "tool_calls": serialized_tcs,
                }
            )
            store.save_messages(messages)

            if not tool_calls:
                await self.broadcast(
                    {
                        "type": "turn_complete",
                        "conversation_id": conversation_id,
                    }
                )
                break

            # Execute requested tool calls
            tool_results: List[Dict[str, Any]] = []
            stop_after_feedback_request = False

            for tc in tool_calls:
                approved = await self._check_hitl_approval_if_needed(conversation_id, tc)
                if not approved:
                    output = "Command execution was denied by the user."
                    is_err = True
                else:
                    try:
                        output = await execute_tool(
                            name=tc.name,
                            args=tc.arguments,
                            store=store,
                            on_event=lambda ev: self.broadcast({**ev, "conversation_id": conversation_id}),
                            wait_for_user_question=lambda qs: self._wait_for_question(conversation_id, qs),
                        )
                        is_err = output.startswith("Error:")
                    except Exception as exc:
                        output = f"Error executing {tc.name}: {exc}"
                        is_err = True

                tool_results.append(
                    {
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "output": output,
                        "is_error": is_err,
                    }
                )

                await self.broadcast(
                    {
                        "type": "tool_call_result",
                        "conversation_id": conversation_id,
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "output": output[:4000],
                        "is_error": is_err,
                    }
                )

                if tc.name in ("write_file", "edit_file"):
                    meta = tc.arguments.get("ArtifactMetadata") or {}
                    if meta.get("RequestFeedback"):
                        stop_after_feedback_request = True

            messages.append({"role": "tool", "tool_results": tool_results})
            store.save_messages(messages)

            if stop_after_feedback_request:
                await self.broadcast(
                    {
                        "type": "turn_complete",
                        "conversation_id": conversation_id,
                        "awaiting_artifact_feedback": True,
                    }
                )
                break

        return final_text

    # ------------------------------------------------------------------
    # Reactive Wakeup Handlers (Subagents, Scheduler, Background Tasks)
    # ------------------------------------------------------------------
    async def _run_subagent_background(
        self,
        instance: SubagentInstance,
        spec: SubagentTypeSpec,
    ) -> None:
        await self.broadcast(
            {
                "type": "subagent_update",
                "subagents": subagent_manager.list_all_instances(),
            }
        )
        sub_store = ConversationStore(instance.conversation_id)
        sub_messages = [{"role": "user", "content": instance.prompt}]
        sub_store.save_messages(sub_messages)

        try:
            result_text = await self._run_agent_loop(
                store=sub_store,
                messages=sub_messages,
                include_write_tools=spec.enable_write_tools,
                include_subagent_tools=spec.enable_subagent_tools,
                include_mcp_tools=spec.enable_mcp_tools,
                custom_system_prompt=spec.system_prompt,
                max_iterations=8,
            )
            instance.status = "completed"
            instance.last_output = result_text
        except Exception as exc:
            instance.status = "failed"
            instance.last_output = f"Subagent failed: {exc}"

        await self.broadcast(
            {
                "type": "subagent_update",
                "subagents": subagent_manager.list_all_instances(),
            }
        )

        # Reactive Wakeup to parent conversation!
        wakeup_msg = (
            f"[REACTIVE WAKEUP — Subagent `{instance.conversation_id}` ({instance.role}) completed]\n\n"
            f"{instance.last_output}"
        )
        await self.handle_user_message(
            conversation_id=instance.parent_conversation_id,
            user_text=wakeup_msg,
        )

    async def _on_scheduler_wakeup(self, conversation_id: str, job_id: str, prompt: str) -> None:
        wakeup_msg = f"[SCHEDULED TRIGGER `{job_id}`]: {prompt}"
        await self.handle_user_message(conversation_id=conversation_id, user_text=wakeup_msg)

    async def _on_terminal_wakeup(self, payload: Dict[str, Any]) -> None:
        await self.broadcast(payload)
        # If the task had transitioned to background (went_async=True) and is not an infinite daemon,
        # automatically wake up the parent agent conversation so the user never has to ask "que paso?"
        conv_id = payload.get("conversation_id")
        if conv_id and payload.get("went_async") and not payload.get("is_daemon"):
            wakeup_msg = (
                f"[REACTIVE WAKEUP — Background Task `{payload['task_id']}` ({payload.get('tool_summary')}) finished "
                f"with status={payload.get('status')} (exit_code={payload.get('exit_code')})]\n"
                f"Command: `{payload.get('command_line')}`\n"
                f"Output:\n{payload.get('recent_output') or '(No output)'}"
            )
            asyncio.create_task(
                self.handle_user_message(
                    conversation_id=conv_id,
                    user_text=wakeup_msg,
                )
            )


orchestrator = AgentOrchestrator()
