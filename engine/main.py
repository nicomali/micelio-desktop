"""
FastAPI + WebSocket Backend Server for Micelio Desktop (`engine/main.py`).

Exposes:
- `/ws`: Real-time bidirectional WebSocket for streaming agent responses, thinking,
  tool calls, artifacts, `ask_question` cards, and HITL approvals.
- `/api/config`: Get/update non-sensitive configuration (`Phoenix`, `Boto3`, `Anthropic`, `Atlassian`, `GitHub`).
- `/api/credentials`: Read/write/delete/enumerate secrets in the **Windows Credential Manager (WinCred)**.
- `/api/conversations`: List conversations, messages, and artifacts.
- `/api/workspace/tree`: File explorer tree for the active workspace.
- `/api/tasks` & `/api/subagents`: Live status of background processes, cron schedules, and subagents.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.config import config_manager
from engine.core.agent import orchestrator
from engine.core.scheduler import scheduler_manager
from engine.core.subagents import subagent_manager
from engine.core.transcript import ConversationStore, list_all_conversations
from engine.mcp_host.manager import mcp_host
from engine.skills.loader import discover_skills
from engine.tools.filesystem import IGNORE_DIRS
from engine.tools.terminal import terminal_manager

app = FastAPI(title="Micelio Desktop Core Engine (Santander)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecretWritePayload(BaseModel):
    key: str
    secret: str
    custom_target: Optional[str] = None
    username: Optional[str] = None


class TargetMapPayload(BaseModel):
    key: str
    target_name: str


class ChatMessagePayload(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    provider_override: Optional[str] = None


class ArtifactFeedbackPayload(BaseModel):
    conversation_id: str
    artifact_name: str
    approved: bool
    comments: Optional[str] = None


@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "micelio-engine",
        "active_provider": config_manager.config.active_provider,
        "active_workspace": config_manager.config.active_workspace,
    }


@app.get("/api/config")
async def get_config() -> Dict[str, Any]:
    return config_manager.config.model_dump()


@app.post("/api/config")
async def update_config(patch: Dict[str, Any]) -> Dict[str, Any]:
    updated = config_manager.update(patch)
    return updated.model_dump()


# ---------------------------------------------------------------------------
# Windows Credential Manager (WinCred) Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/credentials")
async def get_credentials_status() -> Dict[str, Any]:
    return {
        "credentials": [asdict(c) for c in config_manager.vault.list_status()],
        "windows_targets": config_manager.vault.enumerate_windows_targets(),
    }


@app.post("/api/credentials")
async def save_credential_to_wincred(payload: SecretWritePayload) -> Dict[str, Any]:
    if payload.custom_target:
        config_manager.config.custom_wincred_targets[payload.key] = payload.custom_target
        config_manager.save()
    ok = config_manager.vault.set_secret(
        key=payload.key,
        secret=payload.secret,
        custom_target=payload.custom_target,
        username=payload.username,
    )
    return {
        "ok": ok,
        "credentials": [asdict(c) for c in config_manager.vault.list_status()],
    }


@app.post("/api/credentials/link-target")
async def link_existing_windows_target(payload: TargetMapPayload) -> Dict[str, Any]:
    """Point a Micelio credential key to an existing TargetName in Windows Credential Manager."""
    config_manager.vault.set_custom_target(payload.key, payload.target_name)
    config_manager.config.custom_wincred_targets[payload.key] = payload.target_name
    config_manager.save()
    return {
        "ok": True,
        "credentials": [asdict(c) for c in config_manager.vault.list_status()],
    }


@app.delete("/api/credentials/{key}")
async def delete_credential_from_wincred(key: str) -> Dict[str, Any]:
    ok = config_manager.vault.delete_secret(key)
    return {
        "ok": ok,
        "credentials": [asdict(c) for c in config_manager.vault.list_status()],
    }


# ---------------------------------------------------------------------------
# Conversations, Artifacts, Workspace, MCPs, Skills, Tasks
# ---------------------------------------------------------------------------
@app.get("/api/conversations")
async def get_conversations() -> Dict[str, Any]:
    return {"conversations": list_all_conversations()}


@app.post("/api/conversations/new")
async def create_conversation() -> Dict[str, Any]:
    cid = str(uuid.uuid4())
    store = ConversationStore(cid)
    store.save_messages([])
    return {"conversation_id": cid, "artifact_dir": str(store.brain_dir)}


@app.get("/api/conversations/{conversation_id}")
async def get_conversation_detail(conversation_id: str) -> Dict[str, Any]:
    store = ConversationStore(conversation_id)
    return {
        "conversation_id": conversation_id,
        "messages": store.load_messages(),
        "artifacts": store.list_artifacts(),
    }


@app.post("/api/artifacts/feedback")
async def submit_artifact_feedback(payload: ArtifactFeedbackPayload) -> Dict[str, Any]:
    if payload.approved:
        text = (
            f"Comments on artifact `{payload.artifact_name}`:\n"
            f"The user has approved this document. Proceed with implementation."
        )
        if payload.comments:
            text += f"\nAdditional notes: {payload.comments}"
    else:
        text = (
            f"Comments on artifact `{payload.artifact_name}`:\n"
            f"Please update the plan based on this feedback: {payload.comments or 'Revise plan.'}"
        )
    asyncio.create_task(
        orchestrator.handle_user_message(
            conversation_id=payload.conversation_id,
            user_text=text,
        )
    )
    return {"ok": True}


@app.get("/api/workspace/tree")
async def get_workspace_tree(max_entries: int = 120) -> Dict[str, Any]:
    root = Path(config_manager.config.active_workspace)
    entries: List[Dict[str, Any]] = []
    if root.exists():
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = sorted([d for d in dirs if d not in IGNORE_DIRS])
            rel_dir = Path(dirpath).relative_to(root)
            for fname in sorted(files):
                rel_file = rel_dir / fname if str(rel_dir) != "." else Path(fname)
                entries.append(
                    {
                        "name": fname,
                        "rel_path": str(rel_file).replace("\\", "/"),
                        "abs_path": str((Path(dirpath) / fname).resolve()).replace("\\", "/"),
                    }
                )
                if len(entries) >= max_entries:
                    break
            if len(entries) >= max_entries:
                break
    return {
        "workspace": str(root.resolve()).replace("\\", "/"),
        "files": entries,
    }


@app.get("/api/workspace/browse")
async def browse_filesystem(path: Optional[str] = None) -> Dict[str, Any]:
    """Browse directories on the machine so the user can pick a workspace from the UI."""
    target = Path(path) if path else Path(config_manager.config.active_workspace)
    if not target.exists() or not target.is_dir():
        target = Path.home()
    target = target.resolve()

    parent = str(target.parent).replace("\\", "/") if target.parent != target else None
    folders: List[Dict[str, str]] = []
    try:
        for item in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if item.is_dir() and not item.name.startswith(".") and item.name not in IGNORE_DIRS:
                folders.append(
                    {
                        "name": item.name,
                        "path": str(item).replace("\\", "/"),
                    }
                )
    except Exception:
        pass

    # Quick roots (Home, Desktop, Projects if exists)
    quick_roots: List[Dict[str, str]] = []
    home = Path.home()
    for label, candidate in [
        ("Home", home),
        ("Escritorio", home / "OneDrive" / "Escritorio"),
        ("Desktop", home / "Desktop"),
        ("Proyectos", home / "OneDrive" / "Escritorio" / "Proyectos"),
    ]:
        if candidate.exists() and candidate.is_dir():
            quick_roots.append({"label": label, "path": str(candidate.resolve()).replace("\\", "/")})

    return {
        "current": str(target).replace("\\", "/"),
        "parent": parent,
        "folders": folders[:100],
        "quick_roots": quick_roots,
    }


@app.get("/api/runtime-status")
async def get_runtime_status() -> Dict[str, Any]:
    return {
        "tasks": terminal_manager.list_tasks_snapshot(),
        "subagents": subagent_manager.list_all_instances(),
        "schedules": scheduler_manager.list_jobs(),
        "skills": discover_skills(),
        "mcp_tools": [
            {"name": t.name, "description": t.description}
            for t in mcp_host.get_all_mcp_tools()
        ],
    }


# ---------------------------------------------------------------------------
# Real-time WebSocket Event Stream
# ---------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()

    async def send_event(ev: Dict[str, Any]) -> None:
        try:
            await ws.send_json(ev)
        except Exception:
            pass

    orchestrator.add_event_listener(send_event)
    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")
            if action == "chat":
                cid = data.get("conversation_id") or str(uuid.uuid4())
                msg = data.get("message", "")
                prov = data.get("provider_override")
                asyncio.create_task(
                    orchestrator.handle_user_message(
                        conversation_id=cid,
                        user_text=msg,
                        provider_override=prov,
                    )
                )
            elif action == "answer_question":
                orchestrator.resolve_question(
                    conversation_id=data["conversation_id"],
                    answers=data.get("answers", {}),
                )
            elif action == "resolve_approval":
                orchestrator.resolve_approval(
                    approval_id=data["approval_id"],
                    approved=bool(data.get("approved", False)),
                )
    except WebSocketDisconnect:
        pass
    finally:
        orchestrator.remove_event_listener(send_event)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("MICELIO_ENGINE_PORT", "8765"))
    uvicorn.run("engine.main:app", host="127.0.0.1", port=port, reload=False)
