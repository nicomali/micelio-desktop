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
        "path": str(skill_md_path.resolve()),
    }


def discover_skills() -> List[Dict[str, str]]:
    roots: List[Path] = [
        Path(__file__).resolve().parent.parent.parent / "skills",
        get_app_data_dir() / "skills",
        Path(config_manager.config.active_workspace) / ".micelio" / "skills",
    ]
    seen: Dict[str, Dict[str, str]] = {}
    for root in roots:
        if not root.exists():
            continue
        for skill_md in root.glob("*/SKILL.md"):
            info = parse_skill_frontmatter(skill_md)
            seen[info["name"]] = info
    return list(seen.values())
