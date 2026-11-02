"""
Atlassian Cloud (Jira + Confluence) & GitHub.com MCP Connectors + Generic MCP Host.

Provides:
1. Built-in high-speed async connectors for **Atlassian Cloud (Jira + Confluence)** and
   **GitHub.com** that read API tokens directly from the **Windows Credential Manager**
   (`atlassian_api_token` and `github_pat`) in memory — works out of the box with zero
   external Node/uv setup required!
2. Standard **MCP JSON-RPC 2.0 Client (`stdio` & `SSE`)** for spawning any external MCP
   server (`@modelcontextprotocol/server-github`, `mcp-atlassian`, or custom Santander MCPs),
   automatically injecting secrets from Windows Credential Manager into the child process's
   in-memory environment.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any, Dict, List, Optional
import httpx

from engine.config import CustomMCPServerConfig, config_manager
from engine.llm.base import ToolDefinition


# ===========================================================================
# 1. Native GitHub.com Connector (Reads `github_pat` from Windows Credential Manager)
# ===========================================================================
class GitHubMCPConnector:
    def _headers(self) -> Dict[str, str]:
        pat = config_manager.vault.get_secret("github_pat")
        if not pat:
            raise RuntimeError(
                "Falta el Personal Access Token de GitHub (`github_pat`). "
                "Guárdalo en el Administrador de Credenciales de Windows desde el panel de Credenciales de Micelio."
            )
        return {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _base_url(self) -> str:
        return config_manager.config.github.api_base_url.rstrip("/")

    def get_tools(self) -> List[ToolDefinition]:
        if not config_manager.config.github.enabled:
            return []
        return [
            ToolDefinition(
                name="github_search_repositories",
                description="[MCP GitHub] Search GitHub repositories by query.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query (e.g. 'org:santander language:python')"},
                        "per_page": {"type": "integer", "description": "Max results (default 10)"},
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name="github_list_pull_requests",
                description="[MCP GitHub] List Pull Requests for a repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string", "description": "Repository owner or org"},
                        "repo": {"type": "string", "description": "Repository name"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "PR state"},
                    },
                    "required": ["owner", "repo"],
                },
            ),
            ToolDefinition(
                name="github_create_pull_request",
                description="[MCP GitHub] Create a new Pull Request in a GitHub repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "head": {"type": "string", "description": "Source branch name"},
                        "base": {"type": "string", "description": "Target branch name (e.g. main)"},
                    },
                    "required": ["owner", "repo", "title", "head", "base"],
                },
            ),
            ToolDefinition(
                name="github_list_issues",
                description="[MCP GitHub] List issues in a GitHub repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    },
                    "required": ["owner", "repo"],
                },
            ),
            ToolDefinition(
                name="github_create_issue",
                description="[MCP GitHub] Create an issue in a GitHub repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "labels": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["owner", "repo", "title"],
                },
            ),
            ToolDefinition(
                name="github_get_file_contents",
                description="[MCP GitHub] Get the contents of a file from a remote GitHub repository.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "path": {"type": "string"},
                        "ref": {"type": "string", "description": "Branch or commit SHA"},
                    },
                    "required": ["owner", "repo", "path"],
                },
            ),
        ]

    async def execute(self, name: str, args: Dict[str, Any]) -> str:
        base = self._base_url()
        headers = self._headers()
        async with httpx.AsyncClient(timeout=25.0) as client:
            if name == "github_search_repositories":
                r = await client.get(
                    f"{base}/search/repositories",
                    params={"q": args["query"], "per_page": args.get("per_page", 10)},
                    headers=headers,
                )
                r.raise_for_status()
                items = r.json().get("items", [])
                return json.dumps(
                    [
                        {
                            "full_name": it["full_name"],
                            "description": it.get("description"),
                            "html_url": it["html_url"],
                            "default_branch": it.get("default_branch"),
                            "private": it.get("private"),
                        }
                        for it in items
                    ],
                    indent=2,
                )

            elif name == "github_list_pull_requests":
                owner = args.get("owner") or config_manager.config.github.default_owner
                repo = args.get("repo") or config_manager.config.github.default_repo
                r = await client.get(
                    f"{base}/repos/{owner}/{repo}/pulls",
                    params={"state": args.get("state", "open"), "per_page": 20},
                    headers=headers,
                )
                r.raise_for_status()
                prs = r.json()
                return json.dumps(
                    [
                        {
                            "number": p["number"],
                            "title": p["title"],
                            "state": p["state"],
                            "user": p.get("user", {}).get("login"),
                            "head": p.get("head", {}).get("ref"),
                            "base": p.get("base", {}).get("ref"),
                            "html_url": p["html_url"],
                        }
                        for p in prs
                    ],
                    indent=2,
                )

            elif name == "github_create_pull_request":
                owner = args["owner"]
                repo = args["repo"]
                r = await client.post(
                    f"{base}/repos/{owner}/{repo}/pulls",
                    json={
                        "title": args["title"],
                        "body": args.get("body", ""),
                        "head": args["head"],
                        "base": args["base"],
                    },
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
                return f"Created PR #{data['number']}: {data['html_url']}"

            elif name == "github_list_issues":
                owner = args["owner"]
                repo = args["repo"]
                r = await client.get(
                    f"{base}/repos/{owner}/{repo}/issues",
                    params={"state": args.get("state", "open"), "per_page": 20},
                    headers=headers,
                )
                r.raise_for_status()
                return json.dumps(
                    [
                        {
                            "number": i["number"],
                            "title": i["title"],
                            "state": i["state"],
                            "html_url": i["html_url"],
                        }
                        for i in r.json()
                    ],
                    indent=2,
                )

            elif name == "github_create_issue":
                owner = args["owner"]
                repo = args["repo"]
                r = await client.post(
                    f"{base}/repos/{owner}/{repo}/issues",
                    json={
                        "title": args["title"],
                        "body": args.get("body", ""),
                        "labels": args.get("labels", []),
                    },
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
                return f"Created Issue #{data['number']}: {data['html_url']}"

            elif name == "github_get_file_contents":
                owner = args["owner"]
                repo = args["repo"]
                path = args["path"].lstrip("/")
                params = {"ref": args["ref"]} if args.get("ref") else {}
                r = await client.get(
                    f"{base}/repos/{owner}/{repo}/contents/{path}",
                    params=params,
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
                if isinstance(data, dict) and data.get("encoding") == "base64":
                    decoded = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                    return decoded
                return json.dumps(data, indent=2)

        return f"Unknown GitHub tool: {name}"


# ===========================================================================
# 2. Native Atlassian Cloud Connector (Jira & Confluence)
# ===========================================================================
class AtlassianMCPConnector:
    def _auth_headers(self) -> tuple[str, Dict[str, str]]:
        cfg = config_manager.config.atlassian
        token = config_manager.vault.get_secret("atlassian_api_token")
        if not token or not cfg.user_email:
            raise RuntimeError(
                "Falta configurar el API Token de Atlassian (`atlassian_api_token` en Windows Credential Manager) "
                "o el Email de usuario en el panel MCP de Atlassian Cloud."
            )
        raw_pair = f"{cfg.user_email.strip()}:{token.strip()}".encode("utf-8")
        basic_b64 = base64.b64encode(raw_pair).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic_b64}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        raw_target = cfg.cloud_url.strip().rstrip("/")
        # If the user entered a raw UUID Cloud ID instead of a https://*.atlassian.net URL,
        # route via https://api.atlassian.com/ex/jira/<cloud_id>
        if raw_target and not raw_target.startswith("http") and "." not in raw_target:
            base_url = f"https://api.atlassian.com/ex/jira/{raw_target}"
        elif raw_target and not raw_target.startswith("http"):
            base_url = f"https://{raw_target}"
        else:
            base_url = raw_target
        return base_url, headers

    @staticmethod
    def _confluence_base(base_url: str) -> str:
        if "api.atlassian.com/ex/jira/" in base_url:
            return base_url.replace("/ex/jira/", "/ex/confluence/")
        return f"{base_url}/wiki"

    def get_tools(self) -> List[ToolDefinition]:
        if not config_manager.config.atlassian.enabled:
            return []
        return [
            ToolDefinition(
                name="jira_search_issues",
                description="[MCP Atlassian Jira] Search Jira issues using JQL (Jira Query Language). Leave jql empty to list recent issues.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "jql": {"type": "string", "description": "JQL query (e.g. 'project = SAN ORDER BY updated DESC')"},
                        "max_results": {"type": "integer", "description": "Max issues to return (default 15)"},
                    },
                },
            ),
            ToolDefinition(
                name="jira_list_projects",
                description="[MCP Atlassian Jira] List all accessible Jira projects in the workspace.",
                input_schema={
                    "type": "object",
                    "properties": {},
                },
            ),
            ToolDefinition(
                name="jira_get_issue",
                description="[MCP Atlassian Jira] Get full details, description, and comments of a Jira issue by key (e.g. SAN-123).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_key": {"type": "string", "description": "Jira issue key (e.g. SAN-123)"},
                    },
                    "required": ["issue_key"],
                },
            ),
            ToolDefinition(
                name="jira_create_issue",
                description="[MCP Atlassian Jira] Create a new issue/ticket in Jira Cloud.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "project_key": {"type": "string", "description": "Jira project key (e.g. SAN)"},
                        "summary": {"type": "string", "description": "Ticket title/summary"},
                        "description": {"type": "string", "description": "Detailed ticket description"},
                        "issue_type": {"type": "string", "description": "Task, Bug, Story (default: Task)"},
                    },
                    "required": ["project_key", "summary"],
                },
            ),
            ToolDefinition(
                name="jira_add_comment",
                description="[MCP Atlassian Jira] Add a comment to an existing Jira issue.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "issue_key": {"type": "string"},
                        "comment": {"type": "string"},
                    },
                    "required": ["issue_key", "comment"],
                },
            ),
            ToolDefinition(
                name="confluence_search_pages",
                description="[MCP Atlassian Confluence] Search Confluence documentation pages using CQL or text query.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "cql": {"type": "string", "description": "CQL query (e.g. 'type=page AND text ~ \"arquitectura\"')"},
                        "limit": {"type": "integer", "description": "Max results (default 10)"},
                    },
                    "required": ["cql"],
                },
            ),
            ToolDefinition(
                name="confluence_get_page",
                description="[MCP Atlassian Confluence] Retrieve the body content of a Confluence page by ID.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "page_id": {"type": "string", "description": "Confluence Page ID"},
                    },
                    "required": ["page_id"],
                },
            ),
        ]

    async def execute(self, name: str, args: Dict[str, Any]) -> str:
        # Reload latest config from disk in case another process or modal updated it
        config_manager.config = config_manager._load()
        base_url, headers = self._auth_headers()
        conf_base = self._confluence_base(base_url)

        async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
            if name == "jira_list_projects":
                r = await client.get(f"{base_url}/rest/api/3/project/search", headers=headers)
                r.raise_for_status()
                projects = r.json().get("values", [])
                return json.dumps(
                    [
                        {
                            "key": p.get("key"),
                            "name": p.get("name"),
                            "projectTypeKey": p.get("projectTypeKey"),
                        }
                        for p in projects
                    ],
                    indent=2,
                    ensure_ascii=False,
                )

            elif name == "jira_search_issues":
                jql = (args.get("jql") or "").strip()
                if not jql:
                    default_proj = config_manager.config.atlassian.default_jira_project.strip()
                    jql = (
                        f"project = \"{default_proj}\" ORDER BY updated DESC"
                        if default_proj
                        else "ORDER BY updated DESC"
                    )
                # Jira Cloud v3 modern endpoint (`/rest/api/3/search/jql`) — replaces deprecated `/rest/api/3/search` (410 Gone)
                r = await client.post(
                    f"{base_url}/rest/api/3/search/jql",
                    json={
                        "jql": jql,
                        "maxResults": int(args.get("max_results", 15)),
                        "fields": ["summary", "status", "assignee", "priority", "issuetype", "updated"],
                    },
                    headers=headers,
                )
                r.raise_for_status()
                issues = r.json().get("issues", [])
                return json.dumps(
                    [
                        {
                            "key": i.get("key"),
                            "summary": i.get("fields", {}).get("summary"),
                            "status": (i.get("fields", {}).get("status") or {}).get("name"),
                            "type": (i.get("fields", {}).get("issuetype") or {}).get("name"),
                            "priority": (i.get("fields", {}).get("priority") or {}).get("name"),
                            "assignee": (i.get("fields", {}).get("assignee") or {}).get("displayName"),
                            "url": f"{base_url}/browse/{i.get('key')}",
                        }
                        for i in issues
                    ],
                    indent=2,
                    ensure_ascii=False,
                )

            elif name == "jira_get_issue":
                key = args["issue_key"]
                r = await client.get(
                    f"{base_url}/rest/api/3/issue/{key}",
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
                fields = data.get("fields", {})
                return json.dumps(
                    {
                        "key": data["key"],
                        "summary": fields.get("summary"),
                        "status": (fields.get("status") or {}).get("name"),
                        "description": fields.get("description"),
                        "url": f"{base_url}/browse/{data['key']}",
                    },
                    indent=2,
                    ensure_ascii=False,
                )

            elif name == "jira_create_issue":
                proj = args.get("project_key") or config_manager.config.atlassian.default_jira_project
                desc_text = args.get("description", "")
                payload = {
                    "fields": {
                        "project": {"key": proj},
                        "summary": args["summary"],
                        "issuetype": {"name": args.get("issue_type", "Task")},
                        "description": {
                            "type": "doc",
                            "version": 1,
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": desc_text}],
                                }
                            ],
                        },
                    }
                }
                r = await client.post(
                    f"{base_url}/rest/api/3/issue",
                    json=payload,
                    headers=headers,
                )
                r.raise_for_status()
                res = r.json()
                return f"Created Jira Issue {res['key']}: {base_url}/browse/{res['key']}"

            elif name == "jira_add_comment":
                key = args["issue_key"]
                payload = {
                    "body": {
                        "type": "doc",
                        "version": 1,
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": args["comment"]}],
                            }
                        ],
                    }
                }
                r = await client.post(
                    f"{base_url}/rest/api/3/issue/{key}/comment",
                    json=payload,
                    headers=headers,
                )
                r.raise_for_status()
                return f"Added comment to {key}."

            elif name == "confluence_search_pages":
                r = await client.get(
                    f"{conf_base}/rest/api/content/search",
                    params={"cql": args["cql"], "limit": args.get("limit", 10)},
                    headers=headers,
                )
                r.raise_for_status()
                results = r.json().get("results", [])
                return json.dumps(
                    [
                        {
                            "id": p.get("id"),
                            "title": p.get("title"),
                            "type": p.get("type"),
                            "url": f"{conf_base}{p.get('_links', {}).get('webui', '')}",
                        }
                        for p in results
                    ],
                    indent=2,
                    ensure_ascii=False,
                )

            elif name == "confluence_get_page":
                pid = args["page_id"]
                r = await client.get(
                    f"{conf_base}/rest/api/content/{pid}",
                    params={"expand": "body.storage,version"},
                    headers=headers,
                )
                r.raise_for_status()
                data = r.json()
                return json.dumps(
                    {
                        "id": data.get("id"),
                        "title": data.get("title"),
                        "version": (data.get("version") or {}).get("number"),
                        "body_html": (data.get("body", {}).get("storage") or {}).get("value", ""),
                    },
                    indent=2,
                    ensure_ascii=False,
                )

        return f"Unknown Atlassian tool: {name}"


# ===========================================================================
# 3. External Stdio JSON-RPC 2.0 MCP Client Session (for custom MCP servers)
# ===========================================================================
class StdioMCPClientSession:
    """Minimal JSON-RPC 2.0 over stdio client for standard MCP servers."""

    def __init__(self, server_cfg: CustomMCPServerConfig) -> None:
        self.cfg = server_cfg
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: List[ToolDefinition] = []
        self._req_id = 0

    async def start(self) -> None:
        if not self.cfg.command:
            return
        env = dict(os.environ)
        env.update(self.cfg.env)
        # Inject secrets from Windows Credential Manager into child process env
        for env_var, target_or_key in self.cfg.wincred_env_map.items():
            secret = config_manager.vault.get_secret(target_or_key)
            if not secret:
                raw = config_manager.vault.read_raw_target(target_or_key)
                secret = raw[0] if raw else None
            if secret:
                env[env_var] = secret

        self.process = await asyncio.create_subprocess_exec(
            self.cfg.command,
            *self.cfg.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        await self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "micelio-desktop", "version": "1.0.0"},
            },
        )
        tools_res = await self._rpc("tools/list", {})
        for t in (tools_res or {}).get("tools", []):
            self.tools.append(
                ToolDefinition(
                    name=f"mcp_{self.cfg.id}_{t['name']}",
                    description=f"[MCP {self.cfg.name}] {t.get('description', '')}",
                    input_schema=t.get("inputSchema", {"type": "object", "properties": {}}),
                )
            )

    async def _rpc(self, method: str, params: Dict[str, Any]) -> Any:
        if not self.process or not self.process.stdin or not self.process.stdout:
            return None
        self._req_id += 1
        req = {"jsonrpc": "2.0", "id": self._req_id, "method": method, "params": params}
        line = json.dumps(req) + "\n"
        self.process.stdin.write(line.encode("utf-8"))
        await self.process.stdin.drain()
        resp_line = await asyncio.wait_for(self.process.stdout.readline(), timeout=15.0)
        if not resp_line:
            return None
        parsed = json.loads(resp_line.decode("utf-8", errors="replace"))
        return parsed.get("result")

    async def call_tool(self, raw_tool_name: str, arguments: Dict[str, Any]) -> str:
        prefix = f"mcp_{self.cfg.id}_"
        actual_name = raw_tool_name[len(prefix) :] if raw_tool_name.startswith(prefix) else raw_tool_name
        res = await self._rpc("tools/call", {"name": actual_name, "arguments": arguments})
        return json.dumps(res, indent=2, ensure_ascii=False)


class MCPHostManager:
    def __init__(self) -> None:
        self.github = GitHubMCPConnector()
        self.atlassian = AtlassianMCPConnector()
        self.custom_sessions: Dict[str, StdioMCPClientSession] = {}

    def get_all_mcp_tools(self) -> List[ToolDefinition]:
        tools: List[ToolDefinition] = []
        tools.extend(self.github.get_tools())
        tools.extend(self.atlassian.get_tools())
        for session in self.custom_sessions.values():
            tools.extend(session.tools)
        return tools

    async def execute_mcp_tool(self, name: str, args: Dict[str, Any]) -> Optional[str]:
        if name.startswith("github_"):
            return await self.github.execute(name, args)
        if name.startswith("jira_") or name.startswith("confluence_"):
            return await self.atlassian.execute(name, args)
        for srv_id, session in self.custom_sessions.items():
            if name.startswith(f"mcp_{srv_id}_"):
                return await session.call_tool(name, args)
        return None


mcp_host = MCPHostManager()
