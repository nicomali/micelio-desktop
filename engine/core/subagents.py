"""
Subagent Definition, Invocation, and Inter-Agent Messaging (`define_subagent`, `invoke_subagent`,
`send_message`, `manage_subagents`).

Includes built-in subagents matching Antigravity:
- `self`: Inherits the parent agent's full capabilities (write tools, terminal, MCPs).
- `research`: Read-only codebase, Jira/Confluence, and GitHub researcher running in an isolated context.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


@dataclass
class SubagentTypeSpec:
    name: str
    description: str
    system_prompt: str
    enable_write_tools: bool = False
    enable_mcp_tools: bool = True
    enable_subagent_tools: bool = False


@dataclass
class SubagentInstance:
    conversation_id: str
    parent_conversation_id: str
    type_name: str
    role: str
    prompt: str
    model: str
    workspace_mode: str
    status: str = "running"  # "running" | "completed" | "failed" | "killed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_output: str = ""
    task: Optional[asyncio.Task] = None


class SubagentManager:
    def __init__(self) -> None:
        self._types: Dict[str, SubagentTypeSpec] = {
            "self": SubagentTypeSpec(
                name="self",
                description="Subagent that inherits the parent agent's full configuration including write tools, terminal, and MCPs.",
                system_prompt="You are an autonomous Micelio subagent (`self`) executing a delegated engineering task for the parent agent.",
                enable_write_tools=True,
                enable_mcp_tools=True,
                enable_subagent_tools=False,
            ),
            "research": SubagentTypeSpec(
                name="research",
                description="Read-only research subagent for exploring the codebase, Jira/Confluence, and GitHub without cluttering the main context.",
                system_prompt=(
                    "You are a specialized read-only Research Subagent (`research`). "
                    "Explore files, search code, and query Jira/Confluence/GitHub MCP tools to return a concise, high-signal report."
                ),
                enable_write_tools=False,
                enable_mcp_tools=True,
                enable_subagent_tools=False,
            ),
        }
        self._instances: Dict[str, SubagentInstance] = {}
        self._runner_cb: Optional[Callable[[SubagentInstance, SubagentTypeSpec], Any]] = None

    def set_runner_callback(self, cb: Callable[[SubagentInstance, SubagentTypeSpec], Any]) -> None:
        self._runner_cb = cb

    def define_subagent(
        self,
        name: str,
        description: str,
        system_prompt: str,
        enable_write_tools: bool = False,
        enable_mcp_tools: bool = True,
        enable_subagent_tools: bool = False,
    ) -> str:
        spec = SubagentTypeSpec(
            name=name,
            description=description,
            system_prompt=system_prompt,
            enable_write_tools=enable_write_tools,
            enable_mcp_tools=enable_mcp_tools,
            enable_subagent_tools=enable_subagent_tools,
        )
        self._types[name] = spec
        return f"Defined subagent type `{name}` successfully."

    def list_types(self) -> List[Dict[str, str]]:
        return [
            {"name": s.name, "description": s.description}
            for s in self._types.values()
        ]

    async def invoke_subagent(
        self,
        parent_conversation_id: str,
        type_name: str,
        role: str,
        prompt: str,
        model: str = "inherit",
        workspace: str = "inherit",
    ) -> str:
        spec = self._types.get(type_name)
        if not spec:
            return f"Error: Subagent type `{type_name}` not found. Available: {', '.join(self._types.keys())}"

        sub_conv_id = f"sub_{uuid.uuid4().hex[:10]}"
        instance = SubagentInstance(
            conversation_id=sub_conv_id,
            parent_conversation_id=parent_conversation_id,
            type_name=type_name,
            role=role,
            prompt=prompt,
            model=model,
            workspace_mode=workspace,
        )
        self._instances[sub_conv_id] = instance

        if self._runner_cb:
            instance.task = asyncio.create_task(self._runner_cb(instance, spec))

        return (
            f"Subagent launched in background.\n"
            f"- conversationId: `{sub_conv_id}`\n"
            f"- Role: {role}\n"
            f"- Type: {type_name}\n"
            f"You will be automatically notified when `{sub_conv_id}` completes and replies."
        )

    def manage_subagents(
        self,
        parent_conversation_id: str,
        action: str,
        conversation_ids: Optional[List[str]] = None,
    ) -> str:
        children = [
            inst
            for inst in self._instances.values()
            if inst.parent_conversation_id == parent_conversation_id
        ]
        if action == "list":
            if not children:
                return "No active or historical subagents for this conversation."
            return "\n".join(
                f"- `{c.conversation_id}` ({c.role} / {c.type_name}): status={c.status}"
                for c in children
            )
        elif action == "kill_all":
            for c in children:
                if c.status == "running" and c.task:
                    c.status = "killed"
                    c.task.cancel()
            return f"Terminated all running subagents ({len(children)})."
        elif action == "kill":
            killed = []
            for cid in conversation_ids or []:
                inst = self._instances.get(cid)
                if inst and inst.status == "running":
                    inst.status = "killed"
                    if inst.task:
                        inst.task.cancel()
                    killed.append(cid)
            return f"Killed subagents: {', '.join(killed) if killed else 'none'}."
        return f"Unknown action: {action}"

    def list_all_instances(self) -> List[Dict[str, Any]]:
        return [
            {
                "conversation_id": i.conversation_id,
                "parent_conversation_id": i.parent_conversation_id,
                "type_name": i.type_name,
                "role": i.role,
                "status": i.status,
                "created_at": i.created_at,
                "last_output": i.last_output[:500],
            }
            for i in self._instances.values()
        ]


subagent_manager = SubagentManager()
