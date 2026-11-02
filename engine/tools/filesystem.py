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

from engine.config import config_manager
from engine.core.transcript import ConversationStore

MAX_READ_LINES = 800
MAX_READ_BYTES = 46080


def resolve_path(raw_path: str, workspace_dir: Optional[str] = None) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        return p
    base = Path(workspace_dir or config_manager.config.active_workspace)
    return (base / p).resolve()


async def tool_read_file(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    path = resolve_path(args["Path"])
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
    if len(output.encode("utf-8")) > MAX_READ_BYTES:
        output = output[:MAX_READ_BYTES] + "\n... [truncated at 46080 bytes]"

    header = f"File: {path} (Showing lines {start_line}-{end_line} of {total_lines})\n"
    return header + output


async def tool_write_file(
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> str:
    path = resolve_path(args["Path"])
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
