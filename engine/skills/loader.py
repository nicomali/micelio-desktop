"""
Discovers and parses `SKILL.md` files from:
1. Built-in project skills (`<repo>/skills/*/SKILL.md`)
2. User global skills (`~/.micelio/skills/*/SKILL.md`)
3. Active workspace skills (`<workspace>/.micelio/skills/*/SKILL.md`)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from engine.config import config_manager, get_app_data_dir

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_skill_frontmatter(skill_md_path: Path) -> Dict[str, str]:
    try:
        text = skill_md_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"name": skill_md_path.parent.name, "description": "Skill", "path": str(skill_md_path)}

    name = skill_md_path.parent.name
    description = "Specialized skill"
    match = _FRONTMATTER_RE.match(text)
    if match:
        for line in match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                v = v.strip().strip('"').strip("'")
                if k == "name" and v:
                    name = v
                elif k == "description" and v:
                    description = v
    return {
        "name": name,
        "description": description,
        "path": str(skill_md_path.resolve()).replace("\\", "/"),
        "content": text,
    }


def discover_skills() -> List[Dict[str, str]]:
    config_manager.config = config_manager._load()
    builtin_root = Path(__file__).resolve().parent.parent.parent / "skills"
    global_root = get_app_data_dir() / "skills"
    ws_dot_root = Path(config_manager.config.active_workspace) / ".micelio" / "skills"
    ws_root = Path(config_manager.config.active_workspace) / "skills"

    roots_with_scope: List[tuple[Path, str]] = [
        (builtin_root, "builtin"),
        (global_root, "global"),
        (ws_dot_root, "project"),
        (ws_root, "project"),
    ]
    seen: Dict[str, Dict[str, str]] = {}
    for root, scope in roots_with_scope:
        if not root.exists():
            continue
        for skill_md in root.glob("*/SKILL.md"):
            info = parse_skill_frontmatter(skill_md)
            info["scope"] = scope
            seen[info["name"]] = info
    return list(seen.values())


def discover_workspace_playbooks() -> List[Dict[str, str]]:
    """
    Discover user-defined Playbooks and Workflows inside the active workspace:
    - `<workspace>/PLAYBOOK.md`, `<workspace>/WORKFLOW.md`, `<workspace>/AGENTS.md`
    - `<workspace>/playbooks/*.md`
    - `<workspace>/.micelio/workflows/*.md`
    - `<workspace>/workflows/*.md`
    """
    config_manager.config = config_manager._load()
    ws = Path(config_manager.config.active_workspace)
    if not ws.exists():
        return []

    candidates: List[Path] = []
    for root_doc in ("PLAYBOOK.md", "WORKFLOW.md", "AGENTS.md"):
        p = ws / root_doc
        if p.exists() and p.is_file():
            candidates.append(p)

    for folder_rel in ("playbooks", "workflows", ".micelio/workflows", ".micelio/playbooks"):
        folder = ws / folder_rel
        if folder.exists() and folder.is_dir():
            candidates.extend(sorted(folder.glob("*.md")))

    playbooks: List[Dict[str, str]] = []
    seen_paths = set()
    for path in candidates:
        resolved = str(path.resolve())
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        info = parse_skill_frontmatter(path)
        title = info["name"] if info["name"] != path.parent.name else path.stem
        playbooks.append(
            {
                "name": title,
                "description": info["description"],
                "path": resolved.replace("\\", "/"),
                "rel_path": str(path.relative_to(ws)).replace("\\", "/"),
            }
        )
    return playbooks
