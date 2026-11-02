"""
AWS Boto3 Provider (`Boto3LambdaBedrockProvider`).

Supports BOTH:
1. Direct AWS Bedrock Runtime (`bedrock-runtime` via `converse_stream` / `converse`)
   with native tool calling and streaming.
2. Corporate AWS Lambda Proxy (`lambda.invoke`) for Santander environments where LLM
   calls go through a centralized governance/audit Lambda function.

Reads AWS credentials from:
- Windows Credential Manager (`aws_access_key_id`, `aws_secret_access_key`, `aws_session_token`)
- OR AWS SSO / IAM Profile (`cfg.aws_profile`)
"""

from __future__ import annotations

import asyncio
import json
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

logger = logging.getLogger("micelio.llm.boto3")


class Boto3LambdaBedrockProvider(LLMProvider):
    provider_id = "boto3"

    def _create_boto3_session(self):
        import boto3

        cfg = config_manager.config.boto3
        vault = config_manager.vault

        access_key = vault.get_secret("aws_access_key_id")
        secret_key = vault.get_secret("aws_secret_access_key")
        session_token = vault.get_secret("aws_session_token")

        session_kwargs: Dict[str, Any] = {"region_name": cfg.aws_region}
        if cfg.aws_profile:
            session_kwargs["profile_name"] = cfg.aws_profile
        elif access_key and secret_key:
            session_kwargs["aws_access_key_id"] = access_key
            session_kwargs["aws_secret_access_key"] = secret_key
            if session_token:
                session_kwargs["aws_session_token"] = session_token

        return boto3.Session(**session_kwargs)

    @staticmethod
    def _to_bedrock_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        bedrock_msgs: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])
            tool_results = msg.get("tool_results", [])

            if role == "assistant":
                blocks: List[Dict[str, Any]] = []
                if isinstance(content, str) and content.strip():
                    blocks.append({"text": content})
                for tc in tool_calls:
                    blocks.append(
                        {
                            "toolUse": {
                                "toolUseId": tc["id"],
                                "name": tc["name"],
                                "input": tc.get("arguments", {}),
                            }
                        }
                    )
                if blocks:
                    bedrock_msgs.append({"role": "assistant", "content": blocks})
            elif role == "tool":
                blocks = []
                for tr in tool_results:
                    blocks.append(
                        {
                            "toolResult": {
                                "toolUseId": tr["tool_call_id"],
                                "content": [{"text": str(tr.get("output", ""))}],
                                "status": "error" if tr.get("is_error") else "success",
                            }
                        }
                    )
                if blocks:
                    bedrock_msgs.append({"role": "user", "content": blocks})
            else:
                text_val = content if isinstance(content, str) else json.dumps(content)
                if text_val.strip():
                    bedrock_msgs.append({"role": "user", "content": [{"text": text_val}]})
        return bedrock_msgs

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[ToolDefinition],
        model_override: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        cfg = config_manager.config.boto3
        if cfg.invocation_mode == "lambda":
            async for chunk in self._invoke_lambda(messages, system_prompt, tools, model_override):
                yield chunk
        else:
            async for chunk in self._invoke_bedrock_converse(messages, system_prompt, tools, model_override):
                yield chunk

    async def _invoke_bedrock_converse(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[ToolDefinition],
        model_override: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        cfg = config_manager.config.boto3
        model_id = model_override or cfg.bedrock_model_id

        def _sync_call():
            session = self._create_boto3_session()
            verify = cfg.ca_bundle_path if cfg.ca_bundle_path else cfg.verify_ssl
            client = session.client("bedrock-runtime", verify=verify)

            converse_kwargs: Dict[str, Any] = {
                "modelId": model_id,
                "messages": self._to_bedrock_messages(messages),
                "system": [{"text": system_prompt}],
            }
            if tools:
                converse_kwargs["toolConfig"] = {
                    "tools": [
                        {
                            "toolSpec": {
                                "name": t.name,
                                "description": t.description,
                                "inputSchema": {"json": t.input_schema},
                            }
                        }
                        for t in tools
                    ]
                }
            return client.converse(**converse_kwargs)

        response = await asyncio.to_thread(_sync_call)
        output_msg = response.get("output", {}).get("message", {})
        for block in output_msg.get("content", []):
            if "reasoningContent" in block:
                r_text = block["reasoningContent"].get("reasoningText", {}).get("text", "")
                if r_text:
                    yield LLMStreamChunk(type="thinking", delta=r_text)
            if "text" in block and block["text"]:
                yield LLMStreamChunk(type="text", delta=block["text"])
            if "toolUse" in block:
                tu = block["toolUse"]
                yield LLMStreamChunk(
                    type="tool_call",
                    tool_call=ToolCallRequest(
                        id=tu.get("toolUseId", f"call_{uuid.uuid4().hex[:8]}"),
                        name=tu["name"],
                        arguments=tu.get("input", {}),
                    ),
                )

    async def _invoke_lambda(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
        tools: List[ToolDefinition],
        model_override: Optional[str] = None,
    ) -> AsyncIterator[LLMStreamChunk]:
        cfg = config_manager.config.boto3
        augmented_system = build_tool_fallback_system_prompt(system_prompt, tools)
        model_id = model_override or cfg.bedrock_model_id

        payload = {
            "model_id": model_id,
            "system": augmented_system,
            "messages": messages,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ],
        }

        def _sync_lambda():
            session = self._create_boto3_session()
            verify = cfg.ca_bundle_path if cfg.ca_bundle_path else cfg.verify_ssl
            lambda_client = session.client("lambda", verify=verify)
            invoke_kwargs: Dict[str, Any] = {
                "FunctionName": cfg.lambda_function_name,
                "InvocationType": "RequestResponse",
                "Payload": json.dumps(payload).encode("utf-8"),
            }
            if cfg.lambda_qualifier:
                invoke_kwargs["Qualifier"] = cfg.lambda_qualifier
            res = lambda_client.invoke(**invoke_kwargs)
            raw_bytes = res["Payload"].read()
            return json.loads(raw_bytes.decode("utf-8"))

        data = await asyncio.to_thread(_sync_lambda)
        if isinstance(data, dict) and "body" in data:
            body = data["body"]
            if isinstance(body, str):
                try:
                    data = json.loads(body)
                except Exception:
                    data = {"content": body}
            elif isinstance(body, dict):
                data = body

        # Check if Lambda returned native tool_calls or plain text
        raw_text = ""
        if isinstance(data, str):
            raw_text = data
        elif isinstance(data, dict):
            raw_text = (
                data.get("content")
                or data.get("completion")
                or data.get("response")
                or data.get("output", "")
            )
            if isinstance(raw_text, list):
                raw_text = "\n".join(
                    b.get("text", "") for b in raw_text if isinstance(b, dict)
                )

        thinking, cleaned_text, parsed_tools = parse_fallback_response(str(raw_text))
        if thinking:
            yield LLMStreamChunk(type="thinking", delta=thinking)
        if cleaned_text:
            yield LLMStreamChunk(type="text", delta=cleaned_text)
        for tc in parsed_tools:
            yield LLMStreamChunk(type="tool_call", tool_call=tc)

        # Also support native tool_calls key if Lambda returns it directly
        if isinstance(data, dict) and isinstance(data.get("tool_calls"), list):
            for tc_raw in data["tool_calls"]:
                yield LLMStreamChunk(
                    type="tool_call",
                    tool_call=ToolCallRequest(
                        id=tc_raw.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                        name=tc_raw["name"],
                        arguments=tc_raw.get("arguments", {}),
                    ),
                )
