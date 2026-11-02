"""
Configuration Manager for Micelio Desktop.
Stores ONLY non-sensitive settings in `~/.micelio/config.json`.
All secrets and tokens are stored in Windows Credential Manager via `engine/credentials.py`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from engine.credentials import WindowsCredentialVault


def get_app_data_dir() -> Path:
    """Return the root data directory (`~/.micelio`), creating it if needed."""
    env_dir = os.environ.get("MICELIO_DATA_DIR")
    base = Path(env_dir) if env_dir else (Path.home() / ".micelio")
    base.mkdir(parents=True, exist_ok=True)
    (base / "brain").mkdir(parents=True, exist_ok=True)
    (base / "skills").mkdir(parents=True, exist_ok=True)
    return base


class PhoenixSettings(BaseModel):
    """Settings for Santander's internal `phoenix` Python library."""
    module_name: str = "phoenix"
    client_class_or_fn: str = "PhoenixClient"
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    environment: str = "san-dev"
    endpoint_url: Optional[str] = None
    extra_kwargs: Dict[str, Any] = Field(default_factory=dict)


class Boto3Settings(BaseModel):
    """Settings for AWS Bedrock Runtime or AWS Lambda Proxy via boto3."""
    invocation_mode: str = "bedrock"  # "bedrock" | "lambda"
    aws_region: str = "eu-west-1"
    aws_profile: Optional[str] = None
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    lambda_function_name: str = "santander-llm-gateway-lambda"
    lambda_qualifier: Optional[str] = None
    verify_ssl: bool = True
    ca_bundle_path: Optional[str] = None


class AnthropicSettings(BaseModel):
    """Settings for local testing with direct Anthropic API Key."""
    model_id: str = "claude-sonnet-4-5"
    max_tokens: int = 8192
    enable_thinking: bool = True
    thinking_budget_tokens: int = 2048


class AtlassianMCPConfig(BaseModel):
    """Configuration for Atlassian Cloud (Jira + Confluence) connector."""
    enabled: bool = True
    cloud_url: str = "https://santander-team.atlassian.net"
    user_email: str = ""
    default_jira_project: str = ""
    default_confluence_space: str = ""
    use_external_mcp_server: bool = False
    external_mcp_command: str = "uvx"
    external_mcp_args: List[str] = Field(default_factory=lambda: ["mcp-atlassian"])


class GitHubMCPConfig(BaseModel):
    """Configuration for GitHub.com connector."""
    enabled: bool = True
    api_base_url: str = "https://api.github.com"
    default_owner: str = ""
    default_repo: str = ""
    use_external_mcp_server: bool = False
    external_mcp_command: str = "npx"
    external_mcp_args: List[str] = Field(
        default_factory=lambda: ["-y", "@modelcontextprotocol/server-github"]
    )


class CustomMCPServerConfig(BaseModel):
    """Any additional stdio or SSE MCP server."""
    id: str
    name: str
    transport: str = "stdio"  # "stdio" | "sse"
    command: Optional[str] = None
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    wincred_env_map: Dict[str, str] = Field(
        default_factory=dict,
        description="Maps ENV_VAR_NAME -> Windows Credential Manager target_name",
    )
    sse_url: Optional[str] = None
    enabled: bool = True


class SecurityPolicySettings(BaseModel):
    """Human-in-the-loop (HITL) approval policies."""
    require_approval_for_commands: bool = False
    require_approval_for_destructive_commands: bool = True
    require_approval_for_external_writes: bool = True
    auto_approved_command_prefixes: List[str] = Field(
        default_factory=lambda: [
            "git status",
            "git diff",
            "git log",
            "git branch",
            "pytest",
            "python --version",
            "node --version",
            "npm test",
            "Get-ChildItem",
            "dir",
            "ls",
        ]
    )


class MicelioConfig(BaseModel):
    active_provider: str = "anthropic"  # "phoenix" | "boto3" | "anthropic"
    active_workspace: str = Field(
        default_factory=lambda: str(Path.cwd())
    )
    phoenix: PhoenixSettings = Field(default_factory=PhoenixSettings)
    boto3: Boto3Settings = Field(default_factory=Boto3Settings)
    anthropic: AnthropicSettings = Field(default_factory=AnthropicSettings)
    atlassian: AtlassianMCPConfig = Field(default_factory=AtlassianMCPConfig)
    github: GitHubMCPConfig = Field(default_factory=GitHubMCPConfig)
    custom_mcp_servers: List[CustomMCPServerConfig] = Field(default_factory=list)
    security: SecurityPolicySettings = Field(default_factory=SecurityPolicySettings)
    custom_wincred_targets: Dict[str, str] = Field(default_factory=dict)


class ConfigManager:
    """Manages persistence of `MicelioConfig` and coordinates with `WindowsCredentialVault`."""

    def __init__(self) -> None:
        self.data_dir = get_app_data_dir()
        self.config_path = self.data_dir / "config.json"
        self.config = self._load()
        self.vault = WindowsCredentialVault(self.config.custom_wincred_targets)

    def _load(self) -> MicelioConfig:
        if self.config_path.exists():
            try:
                raw = json.loads(self.config_path.read_text(encoding="utf-8"))
                return MicelioConfig.model_validate(raw)
            except Exception:
                pass
        default_cfg = MicelioConfig()
        self._save_File(default_cfg)
        return default_cfg

    def _save_File(self, cfg: MicelioConfig) -> None:
        self.config_path.write_text(
            cfg.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def save(self) -> None:
        self._save_File(self.config)

    def update(self, patch: Dict[str, Any]) -> MicelioConfig:
        merged = self.config.model_dump()
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        self.config = MicelioConfig.model_validate(merged)
        for key, target in self.config.custom_wincred_targets.items():
            self.vault.set_custom_target(key, target)
        self.save()
        return self.config


# Singleton instance
config_manager = ConfigManager()
