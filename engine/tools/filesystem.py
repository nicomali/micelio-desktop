"""
Filesystem & Code Search Tools (`read_file`, `write_file`, `edit_file`, `find_by_name`, `grep_search`).
Matches Google Antigravity's tool signatures and behavior, including ArtifactMetadata registration.
"""

from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from engine.config import config_manager, get_app_data_dir
from engine.core.transcript import ConversationStore

MAX_READ_LINES = 800
MAX_READ_BYTES = 46080


def resolve_path(raw_path: str, workspace_dir: Optional[str] = None) -> Path:
    # Always reload latest config so workspace changes from UI take effect immediately
    config_manager.config = config_manager._load()
    cleaned = str(raw_path).strip()
    # Strip leading '@' if the user/model passed an @file mention
    if cleaned.startswith("@"):
        cleaned = cleaned[1:].strip()
    p = Path(cleaned)
    if p.is_absolute():
        # Also handle case where model put @ right before filename in an absolute path (e.g. C:/folder/@file.pptx)
        if p.name.startswith("@"):
            p = p.parent / p.name[1:]
        return p.resolve()
    base = Path(workspace_dir or config_manager.config.active_workspace)
    return (base / p).resolve()


def is_path_within_sandbox(
    target_path: Path,
    store: Optional[ConversationStore] = None,
    allow_builtin_skills: bool = False,
) -> bool:
    """
    Sandbox boundary check: filesystem tools are ONLY allowed inside:
    1. The active workspace directory (`config.active_workspace`)
    2. The Micelio data/brain/scratch/artifacts directory (`~/.micelio/`)
    3. Built-in `skills/` directory (when `allow_builtin_skills=True`)
    """
    try:
        resolved = target_path.resolve()
    except Exception:
        return False
    workspace_root = Path(config_manager.config.active_workspace).resolve()
    micelio_root = (
        store.brain_dir.parent.parent.resolve() if store is not None else get_app_data_dir().resolve()
    )
    allowed_roots = [workspace_root, micelio_root]
    if allow_builtin_skills:
        builtin_skills_root = (Path(__file__).resolve().parent.parent.parent / "skills").resolve()
        allowed_roots.append(builtin_skills_root)

    for allowed_root in allowed_roots:
        try:
            resolved.relative_to(allowed_root)
            return True
        except ValueError:
            continue
    return False


async def tool_read_file(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    path = resolve_path(args["Path"])
    if not is_path_within_sandbox(path, store, allow_builtin_skills=True):
        return (
            f"Error: Sandbox violation — reading files outside the active workspace ({config_manager.config.active_workspace}) "
            f"or scratch directory ({store.scratch_dir}) is blocked for security: {path}"
        )
    if not path.exists():
        return f"Error: File not found: {path}"
    if path.is_dir():
        return f"Error: Path is a directory, not a file: {path}"

    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"Error reading {path}: {exc}"

    lines = raw_text.splitlines()
    total_lines = len(lines)
    start_line = max(1, int(args.get("StartLine") or 1))
    end_line = min(total_lines, int(args.get("EndLine") or min(total_lines, start_line + MAX_READ_LINES - 1)))

    selected = lines[start_line - 1 : end_line]
    numbered = [f"{idx}: {line}" for idx, line in enumerate(selected, start=start_line)]
    output = "\n".join(numbered)
    encoded = output.encode("utf-8")
    if len(encoded) > MAX_READ_BYTES:
        output = (
            encoded[:MAX_READ_BYTES].decode("utf-8", errors="ignore")
            + "\n... [truncated at 46080 bytes]"
        )

    header = f"File: {path} (Showing lines {start_line}-{end_line} of {total_lines})\n"
    return header + output


async def tool_write_file(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    path = resolve_path(args["Path"])
    if not is_path_within_sandbox(path, store):
        return (
            f"Error: Sandbox violation — writing outside the active workspace ({config_manager.config.active_workspace}) "
            f"or scratch directory ({store.scratch_dir}) is blocked for security: {path}"
        )
    content: str = args.get("Content", "")
    overwrite: bool = bool(args.get("Overwrite", False))
    append: bool = bool(args.get("Append", False))
    artifact_meta: Optional[Dict[str, Any]] = args.get("ArtifactMetadata")

    if overwrite and append:
        return "Error: Overwrite and Append cannot both be true."

    if path.exists() and not overwrite and not append:
        return f"Error: File already exists at {path}. Set Overwrite=true or Append=true."

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8") as f:
        f.write(content)

    # Check if this is an artifact or has ArtifactMetadata
    is_in_brain = False
    try:
        path.resolve().relative_to(store.brain_dir.resolve())
        is_in_brain = True
    except ValueError:
        pass

    note = ""
    if artifact_meta or (is_in_brain and path.suffix.lower() == ".md"):
        meta = artifact_meta or {}
        req_feedback = bool(meta.get("RequestFeedback", False))
        entry = store.register_artifact(
            file_path=path,
            summary=meta.get("Summary", f"Artifact {path.name}"),
            user_facing=bool(meta.get("UserFacing", True)),
            request_feedback=req_feedback,
        )
        if on_event:
            await on_event({"type": "artifact_updated", "artifact": entry, "content": content})
        if req_feedback:
            note = "\nNote: You requested user feedback on this artifact. Stop calling tools to end your turn so the user can review it."

    elif on_event:
        await on_event(
            {
                "type": "file_written",
                "path": str(path),
                "lines": len(content.splitlines()),
            }
        )

    return f"Successfully wrote {len(content)} characters to {path}.{note}"


async def tool_edit_file(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    path = resolve_path(args["Path"])
    if not is_path_within_sandbox(path, store):
        return (
            f"Error: Sandbox violation — editing files outside the active workspace ({config_manager.config.active_workspace}) "
            f"is blocked for security: {path}"
        )
    target: str = args.get("Target", "")
    replacement: str = args.get("Replacement", "")
    artifact_meta: Optional[Dict[str, Any]] = args.get("ArtifactMetadata")

    if not path.exists():
        return f"Error: File does not exist: {path}"

    original = path.read_text(encoding="utf-8")
    if target not in original:
        return (
            f"Error: Target string not found in {path}. "
            "Ensure exact whitespace and line breaks match."
        )

    count = original.count(target)
    updated = original.replace(target, replacement)
    path.write_text(updated, encoding="utf-8")

    if artifact_meta:
        entry = store.register_artifact(
            file_path=path,
            summary=artifact_meta.get("Summary", f"Updated {path.name}"),
            user_facing=bool(artifact_meta.get("UserFacing", True)),
            request_feedback=bool(artifact_meta.get("RequestFeedback", False)),
        )
        if on_event:
            await on_event({"type": "artifact_updated", "artifact": entry, "content": updated})

    if on_event:
        await on_event(
            {
                "type": "file_edited",
                "path": str(path),
                "occurrences": count,
                "target": target[:400],
                "replacement": replacement[:400],
            }
        )

    return f"Made {count} replacement(s) in {path}."


IGNORE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}


async def tool_find_by_name(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    search_dir = resolve_path(args.get("SearchDirectory") or config_manager.config.active_workspace)
    if not is_path_within_sandbox(search_dir, store):
        return (
            f"Error: Sandbox violation — searching outside the active workspace ({config_manager.config.active_workspace}) "
            f"is blocked for security: {search_dir}"
        )
    pattern = args.get("Pattern", "*")
    extensions = [e.lstrip(".").lower() for e in (args.get("Extensions") or [])]
    max_depth = int(args.get("MaxDepth") or 8)

    if not search_dir.exists():
        return f"Error: Directory not found: {search_dir}"

    matches: List[str] = []
    base_parts = len(search_dir.parts)

    for root, dirs, files in os.walk(search_dir):
        root_path = Path(root)
        depth = len(root_path.parts) - base_parts
        if depth > max_depth:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for fname in files:
            if extensions:
                ext = Path(fname).suffix.lstrip(".").lower()
                if ext not in extensions:
                    continue
            if fnmatch.fnmatch(fname.lower(), f"*{pattern.lower()}*") or fnmatch.fnmatch(fname, pattern):
                matches.append(str(root_path / fname))
                if len(matches) >= 50:
                    break
        if len(matches) >= 50:
            break

    if not matches:
        return f"No files matching '{pattern}' found in {search_dir}."
    return "\n".join(matches)


async def tool_grep_search(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    search_path = resolve_path(args.get("SearchPath") or config_manager.config.active_workspace)
    if not is_path_within_sandbox(search_path, store):
        return (
            f"Error: Sandbox violation — searching outside the active workspace ({config_manager.config.active_workspace}) "
            f"is blocked for security: {search_path}"
        )
    query: str = args.get("Query", "")
    is_regex: bool = bool(args.get("IsRegex", False))
    case_insensitive: bool = bool(args.get("CaseInsensitive", False))

    if not query:
        return "Error: Query cannot be empty."
    if not search_path.exists():
        return f"Error: SearchPath does not exist: {search_path}"

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(query if is_regex else re.escape(query), flags)
    except re.error as exc:
        return f"Error: Invalid regular expression '{query}': {exc}"

    results: List[str] = []
    files_to_scan: List[Path] = []
    if search_path.is_file():
        files_to_scan.append(search_path)
    else:
        for root, dirs, files in os.walk(search_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                files_to_scan.append(Path(root) / f)

    for fpath in files_to_scan:
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                results.append(f"{fpath}:{line_no}: {line.strip()[:200]}")
                if len(results) >= 60:
                    return "\n".join(results) + "\n... [truncated at 60 matches]"

    if not results:
        return f"No matches found for '{query}' in {search_path}."
    return "\n".join(results)


async def tool_delete_file(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    path = resolve_path(args["Path"])
    if not is_path_within_sandbox(path, store):
        return (
            f"Error: Sandbox violation — deleting files outside the active workspace ({config_manager.config.active_workspace}) "
            f"is blocked for security: {path}"
        )
    if not path.exists():
        return f"Error: File not found: {path}"
    if path.is_dir():
        return f"Error: {path} is a directory, not a file."
    try:
        path.unlink()
    except Exception as exc:
        return f"Error deleting {path}: {exc}"

    if on_event:
        await on_event({"type": "file_deleted", "path": str(path)})
    return f"Successfully deleted file: {path}"
