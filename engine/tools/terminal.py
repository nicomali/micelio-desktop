"""
Asynchronous Terminal & Background Task Manager (`run_command`, `manage_task`).

Matches Antigravity's behavior:
- Runs PowerShell on Windows (or bash on Unix) inside the active workspace.
- Waits `WaitMsBeforeAsync` milliseconds (500–10000ms).
- If the command finishes in time, returns the output synchronously.
- If it exceeds `WaitMsBeforeAsync` or `IsDaemon=true`, transitions into a managed
  Background Task and triggers a **Reactive Wakeup** notification when it finishes.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from engine.config import config_manager


@dataclass
class BackgroundTask:
    task_id: str
    conversation_id: str
    command_line: str
    tool_summary: str
    is_daemon: bool
    created_at: str
    process: asyncio.subprocess.Process
    status: str = "running"  # "running" | "completed" | "failed" | "killed"
    exit_code: Optional[int] = None
    output_lines: List[str] = field(default_factory=list)
    went_async: bool = False


class TerminalTaskManager:
    def __init__(self) -> None:
        self._tasks: Dict[str, BackgroundTask] = {}
        self._wakeup_callbacks: List[Callable[[Dict[str, Any]], Any]] = []

    def register_wakeup_callback(self, cb: Callable[[Dict[str, Any]], Any]) -> None:
        self._wakeup_callbacks.append(cb)

    async def _notify_wakeup(self, payload: Dict[str, Any]) -> None:
        for cb in self._wakeup_callbacks:
            try:
                res = cb(payload)
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    async def run_command(
        self,
        command_line: str,
        tool_summary: str,
        wait_ms_before_async: int = 5000,
        is_daemon: bool = False,
        cwd: Optional[str] = None,
        conversation_id: str = "",
        scratch_dir: Optional[str] = None,
    ) -> str:
        config_manager.config = config_manager._load()
        work_dir = cwd or config_manager.config.active_workspace
        wait_sec = max(0.5, min(10.0, (wait_ms_before_async or 5000) / 1000.0))

        # Force UTF-8 encoding in PowerShell & Python so scripts with accents/emojis never fail on Windows
        if sys.platform == "win32":
            utf8_prelude = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                utf8_prelude + command_line,
            ]
        else:
            cmd = ["/bin/sh", "-c", command_line]

        import os
        from engine.sandbox import sandbox_env

        safe_scratch = scratch_dir or str(Path(work_dir) / ".micelio_scratch")
        env = sandbox_env.build_sandboxed_env(
            workspace_dir=work_dir,
            scratch_dir=safe_scratch,
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.PIPE,
        )

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        bg_task = BackgroundTask(
            task_id=task_id,
            conversation_id=conversation_id,
            command_line=command_line,
            tool_summary=tool_summary,
            is_daemon=is_daemon,
            created_at=datetime.now(timezone.utc).isoformat(),
            process=proc,
        )
        self._tasks[task_id] = bg_task

        reader_future = asyncio.create_task(self._collect_output(bg_task))

        if is_daemon:
            bg_task.went_async = True
            await asyncio.sleep(min(wait_sec, 1.0))
            recent = "".join(bg_task.output_lines[-30:])
            return (
                f"Background daemon task started with TaskId: {task_id} ({tool_summary}).\n"
                f"Initial output:\n{recent or '(running...)'}"
            )

        try:
            await asyncio.wait_for(asyncio.shield(reader_future), timeout=wait_sec)
            out_text = "".join(bg_task.output_lines)
            return (
                f"Command exited with code {bg_task.exit_code}.\n"
                f"Command output:\n{out_text or '(No output)'}"
            )
        except asyncio.TimeoutError:
            bg_task.went_async = True
            recent = "".join(bg_task.output_lines[-25:])
            return (
                f"Command did not finish within {int(wait_sec * 1000)}ms and is continuing in the "
                f"background with TaskId: `{task_id}`.\n"
                f"The system will automatically wake you up when `{task_id}` finishes — STOP calling tools now and end your turn to wait for the notification.\n"
                f"Recent output:\n{recent}"
            )

    async def _collect_output(self, bg_task: BackgroundTask) -> None:
        proc = bg_task.process
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            bg_task.output_lines.append(decoded)
            if len(bg_task.output_lines) > 2000:
                bg_task.output_lines = bg_task.output_lines[-1500:]

        code = await proc.wait()
        bg_task.exit_code = code
        if bg_task.status != "killed":
            bg_task.status = "completed" if code == 0 else "failed"

        await self._notify_wakeup(
            {
                "type": "background_task_completed",
                "task_id": bg_task.task_id,
                "conversation_id": bg_task.conversation_id,
                "went_async": bg_task.went_async,
                "is_daemon": bg_task.is_daemon,
                "command_line": bg_task.command_line,
                "tool_summary": bg_task.tool_summary,
                "status": bg_task.status,
                "exit_code": bg_task.exit_code,
                "recent_output": "".join(bg_task.output_lines[-40:]),
            }
        )

    async def manage_task(
        self,
        action: str,
        task_id: Optional[str] = None,
        input_text: Optional[str] = None,
    ) -> str:
        if action == "list":
            if not self._tasks:
                return "No active or recent background tasks."
            lines = []
            for t in self._tasks.values():
                lines.append(
                    f"- TaskId: `{t.task_id}` | Status: {t.status} | Summary: {t.tool_summary} | Command: `{t.command_line}`"
                )
            return "\n".join(lines)

        if not task_id or task_id not in self._tasks:
            return f"Error: TaskId '{task_id}' not found."

        t = self._tasks[task_id]
        if action == "status":
            recent = "".join(t.output_lines[-50:])
            return (
                f"TaskId: {t.task_id}\nStatus: {t.status}\nExitCode: {t.exit_code}\n"
                f"Recent Output:\n{recent or '(empty)'}"
            )
        elif action == "kill":
            if t.status == "running":
                t.status = "killed"
                try:
                    t.process.kill()
                except Exception:
                    pass
            return f"Task `{task_id}` killed."
        elif action == "send_input":
            if t.status != "running" or not t.process.stdin:
                return f"Error: Task `{task_id}` is not running or does not accept stdin."
            data = (input_text or "") + "\n"
            t.process.stdin.write(data.encode("utf-8"))
            await t.process.stdin.drain()
            return f"Sent input to task `{task_id}`."
        return f"Unknown action: {action}"

    def list_tasks_snapshot(self) -> List[Dict[str, Any]]:
        return [
            {
                "task_id": t.task_id,
                "command_line": t.command_line,
                "tool_summary": t.tool_summary,
                "is_daemon": t.is_daemon,
                "status": t.status,
                "exit_code": t.exit_code,
                "created_at": t.created_at,
                "recent_output": "".join(t.output_lines[-40:]),
            }
            for t in self._tasks.values()
        ]


terminal_manager = TerminalTaskManager()
