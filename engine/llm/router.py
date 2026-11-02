"""
Multi-LLM Router for Micelio Desktop.
Selects between `phoenix` (Santander internal library), `boto3` (AWS Lambda/Bedrock),
and `anthropic` (local API key) dynamically per request or via global config.
"""

from __future__ import annotations

from typing import Dict
from engine.config import config_manager
from engine.llm.anthropic_provider import AnthropicDirectProvider
from engine.llm.base import LLMProvider
from engine.llm.boto3_provider import Boto3LambdaBedrockProvider
from engine.llm.phoenix_provider import PhoenixProvider


class LLMRouter:
    def __init__(self) -> None:
        self._providers: Dict[str, LLMProvider] = {
            "phoenix": PhoenixProvider(),
            "boto3": Boto3LambdaBedrockProvider(),
            "anthropic": AnthropicDirectProvider(),
        }

    def get_provider(self, provider_override: str | None = None) -> LLMProvider:
        key = (provider_override or config_manager.config.active_provider or "anthropic").lower()
        if key not in self._providers:
            key = "anthropic"
        return self._providers[key]


llm_router = LLMRouter()
