"""
End-to-End Verification Suite for Micelio Desktop (`tests/test_engine.py`).

Tests:
1. Windows Credential Manager (WinCred) read/write/delete/enumerate via native `advapi32.dll`.
2. Structured Tool Calling XML/JSON fallback parser (for Santander `phoenix` and AWS Lambda).
3. Built-in tools (`read_file`, `write_file` with `ArtifactMetadata`, `edit_file`, `find_by_name`, `grep_search`, `run_command`).
4. Subagent registration (`self`, `research`, custom) and Skill discovery (`santander-standards`, `git-jira-workflow`).
5. MCP Host tool discovery (`jira_*`, `confluence_*`, `github_*`).
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from engine.core.subagents import subagent_manager
from engine.core.transcript import ConversationStore
from engine.credentials import WindowsCredentialVault
from engine.llm.base import parse_fallback_response
from engine.mcp_host.manager import mcp_host
from engine.skills.loader import discover_skills
from engine.tools.registry import execute_tool, get_builtin_tool_definitions


def test_windows_credential_vault_roundtrip() -> None:
    vault = WindowsCredentialVault()
    test_target = f"micelio-desktop/test_secret_{uuid.uuid4().hex[:6]}"
    secret_value = "san-super-secret-token-2026!"

    # Write into Windows Credential Manager
    ok = vault.write_raw_target(test_target, secret_value, username="santander-test")
    assert ok is True

    # Read back from Windows Credential Manager
    read_res = vault.read_raw_target(test_target)
    assert read_res is not None
    assert read_res[0] == secret_value
    assert read_res[1] == "santander-test"

    # Enumerate targets and verify presence
    targets = vault.enumerate_windows_targets("micelio-desktop/")
    assert any(t["target_name"] == test_target for t in targets)

    # Clean up
    deleted = vault.delete_raw_target(test_target)
    assert deleted is True
    assert vault.read_raw_target(test_target) is None


def test_structured_tool_call_fallback_parser() -> None:
    sample_output = """
    <thinking>
    Necesito buscar los tickets de Jira del proyecto SAN antes de editar el archivo.
    </thinking>
    Voy a consultar los issues activos en Jira Cloud.
    <tool_call>
    {"name": "jira_search_issues", "arguments": {"jql": "project = SAN"}}
    </tool_call>
    """
    thinking, clean_text, tool_calls = parse_fallback_response(sample_output)
    assert "tickets de Jira" in thinking
    assert "Voy a consultar los issues" in clean_text
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "jira_search_issues"
    assert tool_calls[0].arguments == {"jql": "project = SAN"}


def test_mcp_and_skills_discovery() -> None:
    tools = get_builtin_tool_definitions()
    tool_names = {t.name for t in tools}

    # Verify Antigravity core tools
    for expected in (
        "read_file",
        "write_file",
        "edit_file",
        "find_by_name",
        "grep_search",
        "run_command",
        "manage_task",
        "ask_question",
        "schedule",
        "define_subagent",
        "invoke_subagent",
        "manage_subagents",
    ):
        assert expected in tool_names

    # Verify Atlassian & GitHub MCP tools
    mcp_names = {t.name for t in mcp_host.get_all_mcp_tools()}
    assert "jira_search_issues" in mcp_names
    assert "confluence_search_pages" in mcp_names
    assert "github_create_pull_request" in mcp_names

    # Verify Skills discovery
    skills = discover_skills()
    skill_names = {s["name"] for s in skills}
    assert "santander-standards" in skill_names
    assert "git-jira-workflow" in skill_names

    # Verify Subagent types
    sub_types = {s["name"] for s in subagent_manager.list_types()}
    assert "self" in sub_types
    assert "research" in sub_types


def test_filesystem_and_artifact_tools() -> None:
    async def _run():
        conv_id = f"test_conv_{uuid.uuid4().hex[:6]}"
        store = ConversationStore(conv_id)
        artifact_path = store.brain_dir / "implementation_plan.md"

        write_res = await execute_tool(
            "write_file",
            {
                "Path": str(artifact_path),
                "Content": "# Plan\n- Step 1\n",
                "Overwrite": True,
                "ArtifactMetadata": {
                    "Summary": "Test Plan",
                    "UserFacing": True,
                    "RequestFeedback": True,
                },
            },
            store,
        )
        assert "Successfully wrote" in write_res
        assert "requested user feedback" in write_res

        edit_res = await execute_tool(
            "edit_file",
            {
                "Path": str(artifact_path),
                "Target": "- Step 1",
                "Replacement": "- Step 1\n- Step 2",
            },
            store,
        )
        assert "Made 1 replacement" in edit_res

        read_res = await execute_tool(
            "read_file",
            {"Path": str(artifact_path)},
            store,
        )
        assert "Step 2" in read_res

    asyncio.run(_run())
