"""
Conversation Transcript & Artifact Manager (`transcript.jsonl` & `transcript_full.jsonl`).

Mirrors Antigravity's exact storage model:
- Each conversation lives in `~/.micelio/brain/<conversation-id>/`
- Logs live in `~/.micelio/brain/<conversation-id>/.system_generated/logs/transcript.jsonl`
  and `transcript_full.jsonl`
- Artifacts (`.md` plans, walkthroughs, task lists) live directly in
  `~/.micelio/brain/<conversation-id>/<artifact>.md` with metadata stored in `artifacts_meta.json`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from engine.config import get_app_data_dir

COMPACT_FIELD_MAX_CHARS = 2000


class ConversationStore:
    def __init__(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.brain_dir: Path = get_app_data_dir() / "brain" / conversation_id
        self.logs_dir: Path = self.brain_dir / ".system_generated" / "logs"
        self.scratch_dir: Path = self.brain_dir / "scratch"
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

        self.transcript_compact_path = self.logs_dir / "transcript.jsonl"
        self.transcript_full_path = self.logs_dir / "transcript_full.jsonl"
        self.artifacts_meta_path = self.brain_dir / "artifacts_meta.json"
        self.messages_path = self.logs_dir / "messages.json"
        self.meta_path = self.brain_dir / "session_meta.json"
        self._step_counter = self._count_existing_steps()

    def get_session_meta(self) -> Dict[str, Any]:
        if self.meta_path.exists():
            try:
                return json.loads(self.meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save_session_meta(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        meta = self.get_session_meta()
        meta.update(patch)
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta

    def _count_existing_steps(self) -> int:
        if not self.transcript_full_path.exists():
            return 0
        try:
            with self.transcript_full_path.open("r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def append_step(
        self,
        source: str,
        step_type: str,
        status: str = "DONE",
        content: str = "",
        thinking: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        self._step_counter += 1
        now_iso = datetime.now(timezone.utc).isoformat()
        full_entry: Dict[str, Any] = {
            "step_index": self._step_counter,
            "source": source,
            "type": step_type,
            "status": status,
            "created_at": now_iso,
            "content": content,
        }
        if thinking:
            full_entry["thinking"] = thinking
        if tool_calls:
            full_entry["tool_calls"] = tool_calls

        with self.transcript_full_path.open("a", encoding="utf-8") as f_full:
            f_full.write(json.dumps(full_entry, ensure_ascii=False) + "\n")

        compact_entry = dict(full_entry)
        truncated_fields: List[str] = []
        if len(content) > COMPACT_FIELD_MAX_CHARS:
            compact_entry["content"] = content[:COMPACT_FIELD_MAX_CHARS] + "... [truncated]"
            truncated_fields.append("content")
        if thinking and len(thinking) > COMPACT_FIELD_MAX_CHARS:
            compact_entry["thinking"] = thinking[:COMPACT_FIELD_MAX_CHARS] + "... [truncated]"
            truncated_fields.append("thinking")
        if truncated_fields:
            compact_entry["truncated_fields"] = truncated_fields

        with self.transcript_compact_path.open("a", encoding="utf-8") as f_comp:
            f_comp.write(json.dumps(compact_entry, ensure_ascii=False) + "\n")

        return full_entry

    def load_messages(self) -> List[Dict[str, Any]]:
        if not self.messages_path.exists():
            return []
        try:
            return json.loads(self.messages_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def save_messages(self, messages: List[Dict[str, Any]]) -> None:
        self.messages_path.write_text(
            json.dumps(messages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def register_artifact(
        self,
        file_path: Path,
        summary: str,
        user_facing: bool = True,
        request_feedback: bool = False,
    ) -> Dict[str, Any]:
        meta_map: Dict[str, Any] = {}
        if self.artifacts_meta_path.exists():
            try:
                meta_map = json.loads(self.artifacts_meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta_map = {}

        entry = {
            "name": file_path.name,
            "path": str(file_path.resolve()),
            "summary": summary,
            "user_facing": user_facing,
            "request_feedback": request_feedback,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending_review" if request_feedback else "active",
        }
        meta_map[file_path.name] = entry
        self.artifacts_meta_path.write_text(
            json.dumps(meta_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return entry

    def list_artifacts(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        meta_map: Dict[str, Any] = {}
        if self.artifacts_meta_path.exists():
            try:
                meta_map = json.loads(self.artifacts_meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta_map = {}

        for md_file in sorted(self.brain_dir.glob("*.md")):
            info = meta_map.get(md_file.name, {})
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                content = ""
            results.append(
                {
                    "name": md_file.name,
                    "path": str(md_file.resolve()),
                    "summary": info.get("summary", f"Artifact {md_file.name}"),
                    "user_facing": info.get("user_facing", True),
                    "request_feedback": info.get("request_feedback", False),
                    "status": info.get("status", "active"),
                    "updated_at": info.get("updated_at", ""),
                    "content": content,
                }
            )
        return results


def list_all_conversations(project_path: Optional[str] = None) -> List[Dict[str, Any]]:
    brain_root = get_app_data_dir() / "brain"
    convs: List[Dict[str, Any]] = []
    if not brain_root.exists():
        return convs

    norm_filter = str(Path(project_path).resolve()).replace("\\", "/").lower() if project_path else None

    for d in sorted(brain_root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        meta_file = d / "session_meta.json"
        meta: Dict[str, Any] = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                meta = {}

        conv_project = meta.get("project_path", "")
        if norm_filter and conv_project:
            norm_conv = str(Path(conv_project).resolve()).replace("\\", "/").lower()
            if norm_conv != norm_filter:
                continue

        msgs_file = d / ".system_generated" / "logs" / "messages.json"
        title = meta.get("custom_title") or ""
        updated_at = datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc).isoformat()
        if not title and msgs_file.exists():
            try:
                msgs = json.loads(msgs_file.read_text(encoding="utf-8"))
                for m in msgs:
                    if m.get("role") == "user" and isinstance(m.get("content"), str):
                        title = m["content"].strip()[:70]
                        break
            except Exception:
                pass
        if not title:
            title = "Nueva sesión"

        convs.append(
            {
                "id": d.name,
                "title": title,
                "project_path": conv_project,
                "updated_at": updated_at,
                "artifact_dir": str(d.resolve()),
            }
        )
    return convs


def delete_conversation(conversation_id: str) -> bool:
    import shutil

    brain_dir = get_app_data_dir() / "brain" / conversation_id
    if not brain_dir.exists() or not brain_dir.is_dir():
        return False
    try:
        shutil.rmtree(brain_dir)
        return True
    except Exception:
        return False
