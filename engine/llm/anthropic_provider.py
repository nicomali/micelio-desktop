"""
Anthropic Direct Provider (`AnthropicDirectProvider`).

Used for local development and testing with a direct `ANTHROPIC_API_KEY` read from
Windows Credential Manager (`micelio-desktop/anthropic_api_key`) or environment.
Supports native streaming, extended thinking blocks, and native tool calling.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from engine.config import config_manager
from engine.llm.base import LLMProvider, LLMStreamChunk, ToolCallRequest, ToolDefinition

logger = logging.getLogger("micelio.llm.anthropic")


class AnthropicDirectProvider(LLMProvider):
    provider_id = "anthropic"

    def _get_api_key(self) -> str:
        key = config_manager.vault.get_secret("anthropic_api_key")
        if not key:
            raise RuntimeError(
                "No se encontró 'anthropic_api_key' en el Administrador de Credenciales de Windows "
                "ni en la variable de entorno ANTHROPIC_API_KEY. Configúrala desde el panel de Credenciales."
            )
        return key

    @staticmethod
    def _convert_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert internal normalized messages into Anthropic API messages format."""
        anthropic_msgs: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            tool_results = msg.get("tool_results", [])

            if role == "assistant":
                blocks: List[Dict[str, Any]] = []
                if isinstance(content, str) and content.strip():
                    blocks.append({"type": "text", "text": content})
                for tc in tool_calls:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc.get("arguments", {}),
                        }
                    )
                if blocks:
                    anthropic_msgs.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                # Convert tool results to user message with tool_result blocks
                result_blocks: List[Dict[str, Any]] = []
                for tr in tool_results:
                    result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tr["tool_call_id"],
                            "content": str(tr.get("output", "")),
                            "is_error": bool(tr.get("is_error", False)),
                        }
                    )
                if result_blocks:
                    anthropic_msgs.append({"role": "user", "content": result_blocks})
            else:
                if isinstance(content, str) and content.strip():
                    anthropic_msgs.append({"role": "user", "content": content})
                elif isinstance(content, list):
                    anthropic_msgs.append({"role": "user", "content": content})
        return anthropic_msgs

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[ToolDefinition],
        model_override: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        import anthropic

        api_key = self._get_api_key()
        cfg = config_manager.config.anthropic
        model_id = model_override or cfg.model_id

        client = anthropic.AsyncAnthropic(api_key=api_key)
        anthropic_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]
        conv_messages = self._convert_messages(messages)

        kwargs: Dict[str, Any] = {
            "model": model_id,
            "max_tokens": cfg.max_tokens,
            "system": system_prompt,
            "messages": conv_messages,
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        # Fallback chain if the configured model ID is deprecated or not found (404) on the user's tier
        candidate_models = [
            model_id,
            "claude-sonnet-4-5",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ]
        # Deduplicate preserving order
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        last_err: Optional[Exception] = None
        for candidate in models_to_try:
            call_kwargs = dict(kwargs)
            call_kwargs["model"] = candidate
            if cfg.enable_thinking and ("3-7" in candidate or "sonnet-4" in candidate or "opus-4" in candidate):
                if cfg.max_tokens > cfg.thinking_budget_tokens:
                    call_kwargs["thinking"] = {
                        "type": "enabled",
                        "budget_tokens": cfg.thinking_budget_tokens,
                    }
            else:
                call_kwargs.pop("thinking", None)

            current_tool_id: Optional[str] = None
            current_tool_name: Optional[str] = None
            current_tool_json_parts: List[str] = []

            try:
                async with client.messages.stream(**call_kwargs) as stream:
                    async for event in stream:
                        ev_type = getattr(event, "type", "")
                        if ev_type == "content_block_start":
                            block = getattr(event, "content_block", None)
                            b_type = getattr(block, "type", "")
                            if b_type == "tool_use":
                                current_tool_id = getattr(block, "id", "")
                                current_tool_name = getattr(block, "name", "")
                                current_tool_json_parts = []
                        elif ev_type == "content_block_delta":
                            delta = getattr(event, "delta", None)
                            d_type = getattr(delta, "type", "")
                            if d_type == "thinking_delta":
                                yield LLMStreamChunk(
                                    type="thinking",
                                    delta=getattr(delta, "thinking", ""),
                                )
                            elif d_type == "text_delta":
                                yield LLMStreamChunk(
                                    type="text",
                                    delta=getattr(delta, "text", ""),
                                )
                            elif d_type == "input_json_delta":
                                current_tool_json_parts.append(getattr(delta, "partial_json", ""))
                        elif ev_type == "content_block_stop":
                            if current_tool_id and current_tool_name:
                                raw_json = "".join(current_tool_json_parts).strip()
                                try:
                                    parsed_args = json.loads(raw_json) if raw_json else {}
                                except Exception:
                                    parsed_args = {}
                                yield LLMStreamChunk(
                                    type="tool_call",
                                    tool_call=ToolCallRequest(
                                        id=current_tool_id,
                                        name=current_tool_name,
                                        arguments=parsed_args,
                                    ),
                                )
                                current_tool_id = None
                                current_tool_name = None
                                current_tool_json_parts = []
                # Persist working model if fallback succeeded
                if candidate != cfg.model_id:
                    cfg.model_id = candidate
                    config_manager.save()
                return
            except anthropic.NotFoundError as exc:
                last_err = exc
                logger.warning("Model '%s' returned 404 NotFound, trying next fallback...", candidate)
                continue

        if last_err:
            raise last_err
