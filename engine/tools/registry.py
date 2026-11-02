"""
Unified Tool Registry & Dispatcher for Micelio Desktop.

Provides exact Antigravity tool definitions (`read_file`, `write_file`, `edit_file`,
`find_by_name`, `grep_search`, `run_command`, `manage_task`, `ask_question`,
`schedule`, `define_subagent`, `invoke_subagent`, `send_message`, `manage_subagents`)
plus all active MCP tools (`jira_*`, `confluence_*`, `github_*`, and custom MCPs).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from engine.core.scheduler import scheduler_manager
from engine.core.subagents import subagent_manager
from engine.core.transcript import ConversationStore
from engine.llm.base import ToolDefinition
from engine.mcp_host.manager import mcp_host
from engine.tools.filesystem import (
    tool_delete_file,
    tool_edit_file,
    tool_find_by_name,
    tool_grep_search,
    tool_read_file,
    tool_write_file,
)
from engine.tools.terminal import terminal_manager


def get_builtin_tool_definitions(
    include_write_tools: bool = True,
    include_subagent_tools: bool = True,
    include_mcp_tools: bool = True,
) -> List[ToolDefinition]:
    tools: List[ToolDefinition] = [
        ToolDefinition(
            name="read_file",
            description="Read the contents of a text file. Returns at most 800 lines or 46080 bytes.",
            input_schema={
                "type": "object",
                "properties": {
                    "Path": {"type": "string", "description": "The path of the file to read."},
                    "StartLine": {"type": "integer", "description": "Start line to read (1-indexed, inclusive)."},
                    "EndLine": {"type": "integer", "description": "End line to read (inclusive)."},
                },
                "required": ["Path"],
            },
        ),
        ToolDefinition(
            name="find_by_name",
            description="Search for files and subdirectories within a specified directory by filename pattern.",
            input_schema={
                "type": "object",
                "properties": {
                    "SearchDirectory": {"type": "string", "description": "The directory to search within."},
                    "Pattern": {"type": "string", "description": "Pattern to search for."},
                    "Extensions": {"type": "array", "items": {"type": "string"}},
                    "MaxDepth": {"type": "integer"},
                },
                "required": ["SearchDirectory"],
            },
        ),
        ToolDefinition(
            name="grep_search",
            description="Find exact pattern matches within files or directories.",
            input_schema={
                "type": "object",
                "properties": {
                    "SearchPath": {"type": "string", "description": "The path to search."},
                    "Query": {"type": "string", "description": "The search term or regular expression."},
                    "IsRegex": {"type": "boolean"},
                    "CaseInsensitive": {"type": "boolean"},
                },
                "required": ["SearchPath", "Query"],
            },
        ),
        ToolDefinition(
            name="ask_question",
            description="Ask the user one or more multiple-choice questions to clarify requirements and wait for the answers.",
            input_schema={
                "type": "object",
                "properties": {
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "options": {"type": "array", "items": {"type": "string"}},
                                "is_multi_select": {"type": "boolean"},
                            },
                            "required": ["question", "options"],
                        },
                    }
                },
                "required": ["questions"],
            },
        ),
    ]

    if include_write_tools:
        tools.extend(
            [
                ToolDefinition(
                    name="write_file",
                    description="Create a new file or overwrite/append an existing file. When creating an artifact in the brain directory, provide ArtifactMetadata.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "Path": {"type": "string"},
                            "Content": {"type": "string"},
                            "Overwrite": {"type": "boolean"},
                            "Append": {"type": "boolean"},
                            "ArtifactMetadata": {
                                "type": "object",
                                "properties": {
                                    "Summary": {"type": "string"},
                                    "UserFacing": {"type": "boolean"},
                                    "RequestFeedback": {"type": "boolean"},
                                },
                                "required": ["Summary", "UserFacing", "RequestFeedback"],
                            },
                        },
                        "required": ["Path", "Content"],
                    },
                ),
                ToolDefinition(
                    name="edit_file",
                    description="Edit an existing file by replacing an exact Target block with Replacement.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "Path": {"type": "string"},
                            "Target": {"type": "string"},
                            "Replacement": {"type": "string"},
                            "ArtifactMetadata": {
                                "type": "object",
                                "properties": {
                                    "Summary": {"type": "string"},
                                    "UserFacing": {"type": "boolean"},
                                    "RequestFeedback": {"type": "boolean"},
                                },
                            },
                        },
                        "required": ["Path", "Target", "Replacement"],
                    },
                ),
                ToolDefinition(
                    name="delete_file",
                    description="Delete a file inside the active operational workspace folder.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "Path": {
                                "type": "string",
                                "description": "Filename or path to delete (if user wrote @filename, pass filename without '@').",
                            },
                        },
                        "required": ["Path"],
                    },
                ),
                ToolDefinition(
                    name="run_command",
                    description="Execute a PowerShell/shell command in the workspace. Long commands transition to background tasks.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "CommandLine": {"type": "string"},
                            "toolSummary": {"type": "string"},
                            "WaitMsBeforeAsync": {"type": "integer"},
                            "IsDaemon": {"type": "boolean"},
                        },
                        "required": ["CommandLine", "toolSummary", "WaitMsBeforeAsync"],
                    },
                ),
                ToolDefinition(
                    name="manage_task",
                    description="Manage background tasks: 'list', 'status', 'send_input', or 'kill'.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "Action": {"type": "string", "enum": ["list", "status", "send_input", "kill"]},
                            "TaskId": {"type": "string"},
                            "Input": {"type": "string"},
                        },
                        "required": ["Action"],
                    },
                ),
                ToolDefinition(
                    name="schedule",
                    description="Schedule a one-shot timer (DurationSeconds) or recurring cron job (CronExpression) with Reactive Wakeup.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "Prompt": {"type": "string"},
                            "DurationSeconds": {"type": "integer"},
                            "CronExpression": {"type": "string"},
                            "MaxIterations": {"type": "integer"},
                            "IsDaemon": {"type": "boolean"},
                        },
                        "required": ["Prompt"],
                    },
                ),
            ]
        )

    if include_subagent_tools:
        tools.extend(
            [
                ToolDefinition(
                    name="define_subagent",
                    description="Define a new reusable subagent type for this conversation.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "Name": {"type": "string"},
                            "Description": {"type": "string"},
                            "SystemPrompt": {"type": "string"},
                            "EnableWriteTools": {"type": "boolean"},
                            "EnableMCPTools": {"type": "boolean"},
                        },
                        "required": ["Name", "Description", "SystemPrompt"],
                    },
                ),
                ToolDefinition(
                    name="invoke_subagent",
                    description="Launch a subagent ('self', 'research', or custom) in the background.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "TypeName": {"type": "string"},
                            "Role": {"type": "string"},
                            "Prompt": {"type": "string"},
                            "Model": {"type": "string", "enum": ["inherit", "flash_lite", "flash", "pro"]},
                            "Workspace": {"type": "string", "enum": ["inherit", "branch", "share"]},
                        },
                        "required": ["TypeName", "Role", "Prompt"],
                    },
                ),
                ToolDefinition(
                    name="manage_subagents",
                    description="Manage direct subagents: 'list', 'kill', or 'kill_all'.",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "Action": {"type": "string", "enum": ["list", "kill", "kill_all"]},
                            "ConversationIds": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["Action"],
                    },
                ),
            ]
        )

    if include_mcp_tools:
        tools.extend(mcp_host.get_all_mcp_tools())

    return tools


async def execute_tool(
    name: str,
    args: Dict[str, Any],
    store: ConversationStore,
    on_event: Optional[Callable[[Dict[str, Any]], Any]] = None,
    wait_for_user_question: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
) -> str:
    if name == "read_file":
        return await tool_read_file(args, store, on_event)
    elif name == "write_file":
        return await tool_write_file(args, store, on_event)
    elif name == "edit_file":
        return await tool_edit_file(args, store, on_event)
    elif name == "delete_file":
        return await tool_delete_file(args, store, on_event)
    elif name == "find_by_name":
        return await tool_find_by_name(args, store, on_event)
    elif name == "grep_search":
        return await tool_grep_search(args, store, on_event)
    elif name == "run_command":
        return await terminal_manager.run_command(
            command_line=args["CommandLine"],
            tool_summary=args.get("toolSummary", "Run command"),
            wait_ms_before_async=int(args.get("WaitMsBeforeAsync", 5000)),
            is_daemon=bool(args.get("IsDaemon", False)),
            conversation_id=store.conversation_id,
            scratch_dir=str(store.scratch_dir),
        )
    elif name == "manage_task":
        return await terminal_manager.manage_task(
            action=args["Action"],
            task_id=args.get("TaskId"),
            input_text=args.get("Input"),
        )
    elif name == "schedule":
        return await scheduler_manager.schedule(
            conversation_id=store.conversation_id,
            prompt=args["Prompt"],
            duration_seconds=args.get("DurationSeconds"),
            cron_expression=args.get("CronExpression"),
            max_iterations=args.get("MaxIterations"),
            is_daemon=bool(args.get("IsDaemon", False)),
        )
    elif name == "define_subagent":
        return subagent_manager.define_subagent(
            name=args["Name"],
            description=args["Description"],
            system_prompt=args["SystemPrompt"],
            enable_write_tools=bool(args.get("EnableWriteTools", False)),
            enable_mcp_tools=bool(args.get("EnableMCPTools", True)),
        )
    elif name == "invoke_subagent":
        return await subagent_manager.invoke_subagent(
            parent_conversation_id=store.conversation_id,
            type_name=args["TypeName"],
            role=args["Role"],
            prompt=args["Prompt"],
            model=args.get("Model", "inherit"),
            workspace=args.get("Workspace", "inherit"),
        )
    elif name == "manage_subagents":
        return subagent_manager.manage_subagents(
            parent_conversation_id=store.conversation_id,
            action=args["Action"],
            conversation_ids=args.get("ConversationIds"),
        )
    elif name == "ask_question":
        questions = args.get("questions", [])
        if wait_for_user_question:
            answers = await wait_for_user_question(questions)
            return f"User answered:\n{answers}"
        return "Questions presented to user. Waiting for response."

    # Check MCP tools (GitHub, Atlassian Jira/Confluence, Custom MCPs)
    mcp_res = await mcp_host.execute_mcp_tool(name, args)
    if mcp_res is not None:
        return mcp_res

    return f"Error: Unknown tool '{name}'."
