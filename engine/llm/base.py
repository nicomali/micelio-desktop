"""
Unified LLM Abstraction Layer & Structured Tool-Call Fallback Parser.

Why this matters for Santander:
- Anthropic Direct API and AWS Bedrock Converse API support native tool calling.
- However, custom corporate AWS Lambdas or certain wrappers in `phoenix` may only accept
  messages/prompts and return text strings without native `tool_use` blocks.
- `LLMProvider` includes a transparent XML/JSON tool-call protocol fallback so that ANY
  Lambda or `phoenix` endpoint can execute Micelio tools, subagents, and MCP servers reliably.
"""

from __future__ import annotations

import abc
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMStreamChunk:
    """Chunk emitted during LLM generation."""
    type: str  # "thinking" | "text" | "tool_call" | "usage" | "error"
    delta: str = ""
    tool_call: Optional[ToolCallRequest] = None
    usage: Optional[Dict[str, int]] = None


@dataclass
class LLMResponse:
    thinking: str = ""
    content: str = ""
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    stop_reason: str = "end_turn"
    provider_name: str = ""
    model_id: str = ""


TOOL_FALLBACK_INSTRUCTIONS = """
## Structured Tool Calling Protocol
When you need to invoke a tool, emit one or more `<tool_call>` XML blocks in your response using the exact JSON format below:
<tool_call>
{"name": "tool_name_here", "arguments": {"param1": "value1"}}
</tool_call>
Wait for the `<tool_result>` before continuing. If you want to reason before acting, wrap your reasoning inside `<thinking>...</thinking>` tags.
"""


def build_tool_fallback_system_prompt(
    base_system_prompt: str,
    tools: List[ToolDefinition],
) -> str:
    """Inject tool schemas into the system prompt when the backend only accepts text."""
    if not tools:
        return base_system_prompt
    tools_json = [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.input_schema,
        }
        for t in tools
    ]
    return (
        f"{base_system_prompt}\n\n"
        f"{TOOL_FALLBACK_INSTRUCTIONS}\n"
        f"### Available Tools Schema:\n```json\n{json.dumps(tools_json, indent=2)}\n```"
    )


_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_THINKING_RE = re.compile(r"<thinking>\s*(.*?)\s*</thinking>", re.DOTALL)


def parse_fallback_response(raw_text: str) -> tuple[str, str, List[ToolCallRequest]]:
    """
    Extract `<thinking>`, clean user-visible text, and `<tool_call>` blocks from
    plain-text responses returned by `phoenix` or custom AWS Lambdas.
    """
    thinking_parts: List[str] = []
    for match in _THINKING_RE.finditer(raw_text):
        thinking_parts.append(match.group(1).strip())
    cleaned = _THINKING_RE.sub("", raw_text)

    tool_calls: List[ToolCallRequest] = []
    for match in _TOOL_CALL_RE.finditer(cleaned):
        payload_str = match.group(1).strip()
        try:
            payload = json.loads(payload_str)
            name = payload.get("name")
            args = payload.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            if name:
                tool_calls.append(
                    ToolCallRequest(
                        id=payload.get("id") or f"call_{uuid.uuid4().hex[:10]}",
                        name=name,
                        arguments=args if isinstance(args, dict) else {},
                    )
                )
        except Exception:
            continue

    cleaned = _TOOL_CALL_RE.sub("", cleaned).strip()
    return ("\n".join(thinking_parts), cleaned, tool_calls)


class LLMProvider(abc.ABC):
    """Abstract base class for all LLM providers in Micelio Desktop."""

    provider_id: str = "base"

    @abc.abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[ToolDefinition],
        model_override: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        """Stream thinking, text deltas, and tool calls."""
        yield LLMStreamChunk(type="text", delta="")
