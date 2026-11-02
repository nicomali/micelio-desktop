"""
Santander Corporate `phoenix` Library Provider (`PhoenixProvider`).

Wraps Santander's internal `phoenix` Python package so Micelio Desktop can consume
corporate LLMs (AWS Lambda / Bedrock under the hood) directly from Python.

Features:
1. Dynamically imports `phoenix` (or the module configured in `config.phoenix.module_name`).
2. Reads optional corporate credentials from Windows Credential Manager (`phoenix_api_key`, AWS keys).
3. Supports multiple invocation conventions (`client.invoke(...)`, `client.chat(...)`,
   `client.generate(...)`, or callable function) and automatically normalizes tool calls
   via the structured XML/JSON protocol if `phoenix` returns plain text.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from engine.config import config_manager
from engine.llm.base import (
    LLMProvider,
    LLMStreamChunk,
    ToolCallRequest,
    ToolDefinition,
    build_tool_fallback_system_prompt,
    parse_fallback_response,
)

logger = logging.getLogger("micelio.llm.phoenix")


class PhoenixProvider(LLMProvider):
    provider_id = "phoenix"

    def _invoke_phoenix_sync(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[ToolDefinition],
        model_id: str,
    ) -> Any:
        cfg = config_manager.config.phoenix
        vault = config_manager.vault
        phoenix_secret = vault.get_secret("phoenix_api_key")

        try:
            phoenix_mod = importlib.import_module(cfg.module_name)
        except ImportError as exc:
            raise RuntimeError(
                f"No se pudo importar la librería corporativa '{cfg.module_name}' ({exc}). "
                f"Asegúrate de tener instalado el paquete `{cfg.module_name}` en el entorno Python "
                f"de Micelio o cambia temporalmente el proveedor a 'Anthropic' o 'Boto3' en la barra superior."
            ) from exc

        target_attr = getattr(phoenix_mod, cfg.client_class_or_fn, None)
        init_kwargs: Dict[str, Any] = dict(cfg.extra_kwargs)
        if phoenix_secret and "api_key" not in init_kwargs:
            init_kwargs["api_key"] = phoenix_secret
        if cfg.endpoint_url and "endpoint_url" not in init_kwargs:
            init_kwargs["endpoint_url"] = cfg.endpoint_url

        # Prepare structured prompt with tool definitions so Phoenix always supports tool calling
        augmented_system = build_tool_fallback_system_prompt(system_prompt, tools)

        # Build both chat-messages format and unified prompt string so any Phoenix signature works
        flat_prompt_parts = [f"System:\n{augmented_system}\n"]
        for m in messages:
            role = m.get("role", "user").upper()
            content = m.get("content", "")
            if m.get("tool_results"):
                for tr in m["tool_results"]:
                    flat_prompt_parts.append(
                        f"<tool_result id=\"{tr['tool_call_id']}\">\n{tr.get('output', '')}\n</tool_result>"
                    )
            elif content:
                flat_prompt_parts.append(f"{role}:\n{content}\n")
        full_prompt = "\n".join(flat_prompt_parts)

        # Case 1: target_attr is a class (e.g. PhoenixClient / BedrockModel / LLM)
        if isinstance(target_attr, type):
            try:
                client = target_attr(model_id=model_id, **init_kwargs)
            except TypeError:
                client = target_attr(**init_kwargs)

            for method_name in ("chat", "invoke", "generate", "complete", "__call__"):
                method = getattr(client, method_name, None)
                if callable(method):
                    try:
                        return method(
                            messages=messages,
                            system=augmented_system,
                            model=model_id,
                        )
                    except TypeError:
                        return method(full_prompt)

        # Case 2: target_attr is a direct function (e.g. phoenix.invoke(...) or phoenix.ask(...))
        if callable(target_attr):
            try:
                return target_attr(
                    prompt=full_prompt,
                    model_id=model_id,
                    **init_kwargs,
                )
            except TypeError:
                return target_attr(full_prompt)

        # Case 3: fallback to top-level functions on the phoenix module
        for fn_name in ("invoke", "chat", "generate", "ask_llm"):
            fn = getattr(phoenix_mod, fn_name, None)
            if callable(fn):
                return fn(full_prompt)

        raise RuntimeError(
            f"Se importó '{cfg.module_name}', pero no se encontró '{cfg.client_class_or_fn}' "
            "ni un método estándar (`chat`, `invoke`, `generate`). Ajusta el nombre de clase/función "
            "en Configuración -> Proveedor Phoenix."
        )

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[ToolDefinition],
        model_override: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        cfg = config_manager.config.phoenix
        model_id = model_override or cfg.model_id

        raw_result = await asyncio.to_thread(
            self._invoke_phoenix_sync,
            messages,
            system_prompt,
            tools,
            model_id,
        )

        if isinstance(raw_result, dict):
            text_out = (
                raw_result.get("content")
                or raw_result.get("response")
                or raw_result.get("text")
                or raw_result.get("completion")
                or str(raw_result)
            )
            native_tools = raw_result.get("tool_calls", [])
        else:
            text_out = str(raw_result)
            native_tools = []

        thinking, cleaned_text, parsed_tools = parse_fallback_response(text_out)
        if thinking:
            yield LLMStreamChunk(type="thinking", delta=thinking)
        if cleaned_text:
            yield LLMStreamChunk(type="text", delta=cleaned_text)

        for tc in parsed_tools:
            yield LLMStreamChunk(type="tool_call", tool_call=tc)

        for tc_raw in native_tools:
            if isinstance(tc_raw, dict) and tc_raw.get("name"):
                yield LLMStreamChunk(
                    type="tool_call",
                    tool_call=ToolCallRequest(
                        id=tc_raw.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                        name=tc_raw["name"],
                        arguments=tc_raw.get("arguments", {}),
                    ),
                )
