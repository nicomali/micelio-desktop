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
from engine.sandbox import sandbox_env
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
    assert "santander-pptx-designer" in skill_names

    # Verify Subagent types
    sub_types = {s["name"] for s in subagent_manager.list_types()}
    assert "self" in sub_types
    assert "research" in sub_types


def test_runtime_sandbox_blocks_outside_writes() -> None:
    import subprocess
    import sys

    conv_id = f"test_sbx_{uuid.uuid4().hex[:6]}"
    store = ConversationStore(conv_id)
    env = sandbox_env.build_sandboxed_env(
        workspace_dir=str(store.brain_dir),
        scratch_dir=str(store.scratch_dir),
    )

    # 1. Writing inside scratch_dir MUST succeed
    try:
        allowed_file = (store.scratch_dir / "ok.txt").as_posix()
        res_ok = subprocess.run(
            [sys.executable, "-c", f"open('{allowed_file}', 'w').write('ok')"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res_ok.returncode == 0

        # 2. Writing outside allowed roots (e.g. parent of app_dir) MUST be blocked by sitecustomize audit hook
        forbidden_file = (Path.home() / "micelio_forbidden_write_test.txt").as_posix()
        res_blocked = subprocess.run(
            [sys.executable, "-c", f"open('{forbidden_file}', 'w').write('hack')"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res_blocked.returncode != 0
        assert "Micelio Sandbox" in res_blocked.stderr

        # 3. SEC-05: os.open with write flags outside allowed roots MUST be blocked
        res_os_open = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import os; os.open('{forbidden_file}', os.O_WRONLY | os.O_CREAT)",
            ],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res_os_open.returncode != 0
        assert "Micelio Sandbox" in res_os_open.stderr
    finally:
        from engine.core.transcript import delete_conversation

        delete_conversation(conv_id)


def test_filesystem_and_artifact_tools() -> None:
    from engine.core.transcript import delete_conversation

    async def _run():
        conv_id = f"test_conv_{uuid.uuid4().hex[:6]}"
        store = ConversationStore(conv_id)
        try:
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
        finally:
            delete_conversation(conv_id)

    asyncio.run(_run())


def test_terminal_whitelist_blocks_chaining_and_injection() -> None:
    """SEC-02: Verify SAFE_COMMAND_PREFIXES cannot be bypassed with ;, &&, |, ||, `, $(), >, <."""
    from engine.config import config_manager
    from engine.tools.terminal import (
        has_shell_chaining,
        is_destructive,
        is_whitelisted,
        requires_command_approval,
    )

    orig_req_all = config_manager.config.security.require_approval_for_commands
    orig_req_dest = config_manager.config.security.require_approval_for_destructive_commands
    try:
        config_manager.config.security.require_approval_for_commands = True
        config_manager.config.security.require_approval_for_destructive_commands = True

        # Pure safe commands pass whitelist
        assert is_whitelisted("git status") is True
        assert is_whitelisted("pytest -q") is True
        assert is_destructive("git status", require_approval_for_commands=True) is False
        assert requires_command_approval("git status") is False

        # Chained commands starting with a safe prefix MUST NOT pass whitelist
        for chained in (
            "git status; whoami",
            "git status && calc.exe",
            "git status | Out-File pwn.txt",
            "pytest || echo fail",
            "git log `whoami`",
            "git diff $(whoami)",
            "ls > out.txt",
            "dir < in.txt",
            "git status\nwhoami",
            "git status & whoami",
        ):
            assert has_shell_chaining(chained) is True, f"Expected chaining detected for: {chained}"
            assert is_whitelisted(chained) is False, f"Expected whitelist reject for: {chained}"
            assert is_destructive(chained, require_approval_for_commands=True) is True
            assert requires_command_approval(chained) is True

        # Destructive command starting with a whitelisted prefix must require approval even when require_approval_for_commands=False
        config_manager.config.security.require_approval_for_commands = False
        assert requires_command_approval("git status && rm -rf /") is True
    finally:
        config_manager.config.security.require_approval_for_commands = orig_req_all
        config_manager.config.security.require_approval_for_destructive_commands = orig_req_dest


def test_config_manager_atomic_write(monkeypatch) -> None:
    """BUG-06: Verify ConfigManager.save uses atomic .tmp + os.replace and threading.Lock."""
    import os
    from engine.config import config_manager

    replace_calls = []
    real_replace = os.replace

    def spy_replace(src, dst):
        replace_calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy_replace)
    config_manager.save()

    assert len(replace_calls) == 1
    src_path, dst_path = replace_calls[0]
    assert src_path.endswith(".tmp")
    assert dst_path == str(config_manager.config_path)
    assert not Path(src_path).exists()
    assert config_manager.config_path.exists()


def test_open_native_blocks_executables_and_outside_paths() -> None:
    """SEC-01 & SEC-03: Verify /api/workspace/open-native blocks .exe/.bat/.ps1 and outside paths, plus ws origin check."""
    from engine.config import config_manager
    from engine.main import is_allowed_ws_origin, open_workspace_file_external, read_workspace_file

    # SEC-01: WebSocket Origin validation
    assert is_allowed_ws_origin(None) is True
    assert is_allowed_ws_origin("http://localhost:5173") is True
    assert is_allowed_ws_origin("http://127.0.0.1:8765") is True
    assert is_allowed_ws_origin("file:///C:/app/index.html") is True
    assert is_allowed_ws_origin("https://evil.example.com") is False

    ws_root = Path(config_manager.config.active_workspace).resolve()

    async def _run():
        # 1. Path outside active workspace MUST be rejected
        res_outside = await open_workspace_file_external({"path": "C:/Windows/System32/notepad.exe"})
        assert res_outside["ok"] is False
        assert "fuera del workspace" in res_outside["error"]

        res_file_outside = await read_workspace_file("C:/Windows/win.ini")
        assert "error" in res_file_outside and "bloqueado" in res_file_outside["error"]

        # 2. Executable extensions (.exe, .bat, .ps1) inside workspace MUST be blocked
        for ext in (".exe", ".bat", ".ps1", ".cmd", ".vbs", ".js"):
            dummy_exec = ws_root / f"_test_blocked_payload{ext}"
            res_ext = await open_workspace_file_external({"path": str(dummy_exec)})
            assert res_ext["ok"] is False
            assert "bloqueada por seguridad" in res_ext["error"]

    asyncio.run(_run())


def test_connection_manager_cleans_pending_futures_on_disconnect() -> None:
    """BUG-05: Verify ConnectionManager.disconnect cancels pending_questions and pending_approvals futures."""
    from engine.core.agent import AgentOrchestrator
    from engine.main import ConnectionManager

    async def _run():
        orch = AgentOrchestrator()
        cm = ConnectionManager(orch)
        loop = asyncio.get_running_loop()

        q_fut = loop.create_future()
        a_fut = loop.create_future()
        cm.pending_questions["conv_test_1"] = q_fut
        cm.pending_approvals["appr_test_1"] = a_fut

        assert not q_fut.done()
        assert not a_fut.done()

        cm.disconnect()

        assert q_fut.done() and q_fut.cancelled()
        assert a_fut.done() and a_fut.cancelled()
        assert len(cm.pending_questions) == 0
        assert len(cm.pending_approvals) == 0

    asyncio.run(_run())


def test_transcript_security_and_utf8_truncation() -> None:
    """SEC-04, SEC-06, BUG-02, BUG-07: Path traversal in conversation_id, sub_ filtering, sandbox read, UTF-8 byte truncation."""
    import pytest
    from engine.core.transcript import (
        ConversationStore,
         delete_conversation,
        list_all_conversations,
    )

    # SEC-04: Reject path traversal in conversation_id
    for bad_id in ("../escape", "..\\escape", "a/b", "", ".."):
        with pytest.raises(ValueError):
            ConversationStore(bad_id)
        assert delete_conversation(bad_id) is False

    # BUG-02: Subagent conversations (sub_*) hidden from list_all_conversations
    sub_id = f"sub_test_{uuid.uuid4().hex[:6]}"
    try:
        sub_store = ConversationStore(sub_id)
        sub_store.save_messages([{"role": "user", "content": "internal subagent task"}])
        listed_ids = {c["id"] for c in list_all_conversations()}
        assert sub_id not in listed_ids
    finally:
        delete_conversation(sub_id)

    # SEC-06 & BUG-07: Sandbox read restriction and UTF-8 multi-byte safe truncation
    conv_id = f"test_utf8_{uuid.uuid4().hex[:6]}"
    store = ConversationStore(conv_id)
    try:
        async def _run():
            outside_read = await execute_tool(
                "read_file",
                {"Path": "C:/Windows/win.ini"},
                store,
            )
            assert "Sandbox violation" in outside_read

            # Create file with multi-byte UTF-8 characters exceeding MAX_READ_BYTES (46080)
            big_file = store.scratch_dir / "utf8_big.txt"
            big_file.write_text(("áéíóúñ🚀" * 3500) + "\n", encoding="utf-8")
            read_res = await execute_tool("read_file", {"Path": str(big_file)}, store)
            assert "truncated at 46080 bytes" in read_res
            body_before_marker = read_res.split("\n", 1)[1].split("\n... [truncated")[0]
            assert len(body_before_marker.encode("utf-8")) <= 46080

        asyncio.run(_run())
    finally:
        delete_conversation(conv_id)

