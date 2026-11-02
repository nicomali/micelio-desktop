"""
Micelio Execution Sandbox (`engine/sandbox.py`).

Provides two layers of real process isolation on Windows/Unix without requiring Docker:
1. Isolated Virtual Environment (`~/.micelio/sandbox-venv`):
   - When the agent runs `python` or `pip install`, it uses the sandbox venv instead of
     polluting the user's global Windows Python installation.
2. Runtime Python Audit Hook (`sitecustomize.py` inside the sandbox):
   - Uses Python's native `sys.addaudithook` to intercept file write/delete/rename operations
     (`open`, `os.remove`, `os.unlink`, `os.rmdir`, `os.rename`, `os.replace`, `shutil.*`).
   - Allows reading from anywhere (so standard libraries and installed packages work),
     but BLOCKS any write or deletion outside `MICELIO_ALLOWED_WRITE_ROOTS`
     (the active workspace folder, `~/.micelio/`, and the temp scratch directory).
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import venv
from pathlib import Path
from typing import Dict, List

from engine.config import get_app_data_dir

logger = logging.getLogger("micelio.sandbox")

SITECUSTOMIZE_CODE = '''"""
Auto-injected Micelio Runtime Sandbox Audit Hook (`sitecustomize.py`).
Blocks any Python file write, modification, or deletion outside the allowed workspace roots.
"""
import os
import sys
from pathlib import Path

_RAW_ROOTS = os.environ.get("MICELIO_ALLOWED_WRITE_ROOTS", "")
_ALLOWED_ROOTS = [Path(p).resolve() for p in _RAW_ROOTS.split(os.pathsep) if p.strip()]


def _is_path_allowed(target) -> bool:
    if not _ALLOWED_ROOTS:
        return True
    try:
        p = Path(str(target)).resolve()
    except Exception:
        return False
    p_str = str(p).lower()
    # Allow null device
    if p_str in ("nul", "/dev/null", "\\\\?\\nul"):
        return True
    for root in _ALLOWED_ROOTS:
        root_str = str(root).lower()
        if p_str == root_str or p_str.startswith(root_str + os.sep):
            return True
    return False


_WRITE_FLAGS = (
     getattr(os, "O_WRONLY", 1)
    | getattr(os, "O_RDWR", 2)
    | getattr(os, "O_CREAT", 256)
    | getattr(os, "O_TRUNC", 512)
    | getattr(os, "O_APPEND", 8)
)


def _micelio_audit_hook(event: str, args: tuple) -> None:
    if not _ALLOWED_ROOTS:
        return
    if event == "open":
        path_arg = args[0] if len(args) > 0 else None
        mode_arg = args[1] if len(args) > 1 else "r"
        flags_arg = args[2] if len(args) > 2 else 0
        if isinstance(path_arg, (str, bytes, os.PathLike)):
            is_write_mode = isinstance(mode_arg, str) and any(
                m in mode_arg for m in ("w", "a", "x", "+")
            )
            is_write_flags = isinstance(flags_arg, int) and bool(flags_arg & _WRITE_FLAGS)
            if is_write_mode or is_write_flags:
                if not _is_path_allowed(path_arg):
                    raise PermissionError(
                        f"[Micelio Sandbox] Write access denied outside active workspace: {path_arg}"
                    )
    elif event == "os.open":
        path_arg = args[0] if len(args) > 0 else None
        flags_arg = args[1] if len(args) > 1 else 0
        if isinstance(path_arg, (str, bytes, os.PathLike)):
            if isinstance(flags_arg, int) and bool(flags_arg & _WRITE_FLAGS):
                if not _is_path_allowed(path_arg):
                    raise PermissionError(
                        f"[Micelio Sandbox] os.open write denied outside active workspace: {path_arg}"
                    )
    elif event in ("os.remove", "os.unlink", "os.rmdir", "os.mkdir", "shutil.rmtree"):
        path_arg = args[0] if len(args) > 0 else None
        if isinstance(path_arg, (str, bytes, os.PathLike)) and not _is_path_allowed(path_arg):
            raise PermissionError(
                f"[Micelio Sandbox] Modify/Delete access denied outside active workspace: {path_arg}"
            )
    elif event in (
        "os.rename",
        "os.replace",
        "shutil.move",
        "shutil.copyfile",
        "shutil.copy",
        "shutil.copy2",
        "shutil.copytree",
    ):
        src = args[0] if len(args) > 0 else None
        dst = args[1] if len(args) > 1 else None
        check_src = event in ("os.rename", "os.replace", "shutil.move")
        if (check_src and src and not _is_path_allowed(src)) or (dst and not _is_path_allowed(dst)):
            raise PermissionError(
                f"[Micelio Sandbox] Rename/Move/Copy denied outside active workspace: {src} -> {dst}"
            )


if os.environ.get("MICELIO_SANDBOX_ACTIVE") == "1":
    sys.addaudithook(_micelio_audit_hook)
'''


class SandboxEnvironment:
    def __init__(self) -> None:
        self.app_dir = get_app_data_dir()
        self.venv_dir = self.app_dir / "sandbox-venv"
        self.guard_dir = self.app_dir / "sandbox-guard"
        self._initialized = False

    def ensure_ready(self) -> None:
        """Create the sandbox guard (`sitecustomize.py`) and isolated `venv` if not present."""
        self.guard_dir.mkdir(parents=True, exist_ok=True)
        sitecustomize_path = self.guard_dir / "sitecustomize.py"
        sitecustomize_path.write_text(SITECUSTOMIZE_CODE, encoding="utf-8")

        if not self._venv_python_path().exists():
            try:
                logger.info("Creating isolated Micelio sandbox venv at %s...", self.venv_dir)
                venv.create(self.venv_dir, with_pip=True, system_site_packages=True)
            except Exception as exc:
                logger.warning("Could not create sandbox venv (%s), falling back to guard-only mode.", exc)

        self._initialized = True

    def _venv_python_path(self) -> Path:
        if sys.platform == "win32":
            return self.venv_dir / "Scripts" / "python.exe"
        return self.venv_dir / "bin" / "python"

    def _venv_scripts_dir(self) -> Path:
        if sys.platform == "win32":
            return self.venv_dir / "Scripts"
        return self.venv_dir / "bin"

    def build_sandboxed_env(self, workspace_dir: str, scratch_dir: str) -> Dict[str, str]:
        """
        Return environment variables that:
        1. Prepend the isolated `sandbox-venv/Scripts` to `PATH`.
        2. Inject `sitecustomize.py` via `PYTHONPATH` so every Python process runs the audit hook.
        3. Restrict writes to `workspace_dir`, `~/.micelio/`, and `scratch_dir`.
        4. Route `TEMP` / `TMP` into the scratch directory.
        """
        if not self._initialized:
            self.ensure_ready()

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["MICELIO_SANDBOX_ACTIVE"] = "1"
        env["MICELIO_SCRATCH_DIR"] = scratch_dir

        allowed_roots: List[str] = [
            str(Path(workspace_dir).resolve()),
            str(Path(scratch_dir).resolve()),
            str(self.app_dir.resolve()),
        ]
        env["MICELIO_ALLOWED_WRITE_ROOTS"] = os.pathsep.join(allowed_roots)

        # Inject sitecustomize.py guard via PYTHONPATH
        existing_py_path = env.get("PYTHONPATH", "")
        guard_str = str(self.guard_dir.resolve())
        env["PYTHONPATH"] = f"{guard_str}{os.pathsep}{existing_py_path}" if existing_py_path else guard_str

        # Prepend sandbox venv Scripts/bin to PATH so `python` and `pip` use the sandbox venv
        scripts_dir = self._venv_scripts_dir()
        if scripts_dir.exists():
            env["VIRTUAL_ENV"] = str(self.venv_dir.resolve())
            env["PATH"] = f"{scripts_dir.resolve()}{os.pathsep}{env.get('PATH', '')}"

        # Confine temporary files to conversation scratch dir
        scratch_tmp = Path(scratch_dir) / "tmp"
        scratch_tmp.mkdir(parents=True, exist_ok=True)
        env["TEMP"] = str(scratch_tmp.resolve())
        env["TMP"] = str(scratch_tmp.resolve())

        return env


sandbox_env = SandboxEnvironment()
