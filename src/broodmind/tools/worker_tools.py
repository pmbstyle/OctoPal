from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from broodmind.tools.registry import ToolSpec

if TYPE_CHECKING:
    from broodmind.queen.core import Queen


def get_worker_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="list_workers",
            description="List available worker templates with their capabilities.",
            parameters={"type": "object", "properties": {}, "additionalProperties": False},
            permission="worker_manage",
            handler=_tool_list_workers,
        ),
        ToolSpec(
            name="start_worker",
            description="Start a worker task with the specified worker template. Returns run_id and status.",
            parameters={
                "type": "object",
                "properties": {
                    "worker_id": {
                        "type": "string",
                        "description": "ID of the worker template to use (e.g., 'web_researcher', 'web_fetcher'). Use list_workers to see available workers.",
                    },
                    "task": {
                        "type": "string",
                        "description": "Natural language task description for the worker.",
                    },
                    "inputs": {
                        "type": "object",
                        "description": "Task-specific input data.",
                        "additionalProperties": True,
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Override default tools for this task (optional).",
                    },
                    "timeout_seconds": {
                        "type": "number",
                        "description": "Override default timeout (optional).",
                    },
                },
                "required": ["worker_id", "task"],
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_start_worker,
        ),
        ToolSpec(
            name="stop_worker",
            description="Stop a running worker by worker_id.",
            parameters={
                "type": "object",
                "properties": {"worker_id": {"type": "string"}},
                "required": ["worker_id"],
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_stop_worker,
        ),
        ToolSpec(
            name="get_worker_status",
            description="Get the current status and details of a specific worker by ID.",
            parameters={
                "type": "object",
                "properties": {
                    "worker_id": {
                        "type": "string",
                        "description": "The worker ID to check.",
                    }
                },
                "required": ["worker_id"],
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_get_worker_status,
        ),
        ToolSpec(
            name="list_active_workers",
            description="List all active workers (running or completed in the last 10 minutes).",
            parameters={
                "type": "object",
                "properties": {
                    "older_than_minutes": {
                        "type": "number",
                        "description": "Include workers updated in the last N minutes (default: 10).",
                    }
                },
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_list_active_workers,
        ),
        ToolSpec(
            name="get_worker_result",
            description="Get the result/output of a completed worker by ID.",
            parameters={
                "type": "object",
                "properties": {
                    "worker_id": {
                        "type": "string",
                        "description": "The worker ID to get results from.",
                    }
                },
                "required": ["worker_id"],
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_get_worker_result,
        ),
        ToolSpec(
            name="create_worker_template",
            description="Create a new worker template by writing a worker.json file to the workspace.",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Unique worker ID (e.g., 'my_researcher'). Use lowercase with underscores.",
                    },
                    "name": {
                        "type": "string",
                        "description": "Human-readable name (e.g., 'My Researcher').",
                    },
                    "description": {
                        "type": "string",
                        "description": "What this worker does.",
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "Worker's personality, purpose, and instructions.",
                    },
                    "available_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tool names this worker can use (e.g., ['web_search', 'web_fetch']).",
                    },
                    "required_permissions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Permissions needed: 'network', 'filesystem_read', 'filesystem_write', 'exec'.",
                    },
                    "max_thinking_steps": {
                        "type": "number",
                        "description": "Max reasoning iterations (default: 10).",
                    },
                    "default_timeout_seconds": {
                        "type": "number",
                        "description": "Default timeout in seconds (default: 300).",
                    },
                },
                "required": ["id", "name", "description", "system_prompt"],
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_create_worker_template,
        ),
        ToolSpec(
            name="update_worker_template",
            description="Update an existing worker template. Reads the worker.json file, modifies the specified fields, and writes it back.",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Worker ID to update.",
                    },
                    "name": {"type": "string", "description": "New name (optional)."},
                    "description": {"type": "string", "description": "New description (optional)."},
                    "system_prompt": {"type": "string", "description": "New system prompt (optional)."},
                    "available_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tool list (optional).",
                    },
                    "required_permissions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New permissions (optional).",
                    },
                    "max_thinking_steps": {"type": "number", "description": "New max steps (optional)."},
                    "default_timeout_seconds": {"type": "number", "description": "New timeout (optional)."},
                },
                "required": ["id"],
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_update_worker_template,
        ),
        ToolSpec(
            name="delete_worker_template",
            description="Delete a worker template by removing its directory from workspace/workers/.",
            parameters={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Worker ID to delete.",
                    }
                },
                "required": ["id"],
                "additionalProperties": False,
            },
            permission="worker_manage",
            handler=_tool_delete_worker_template,
        ),
    ]


def _tool_list_workers(args: dict[str, object], ctx: dict[str, object]) -> str:
    """List available worker templates."""
    queen: Queen = ctx["queen"]

    templates = queen.store.list_worker_templates()
    template_list = []
    for t in templates:
        template_list.append({
            "worker_id": t.id,
            "name": t.name,
            "description": t.description,
            "available_tools": t.available_tools,
            "required_permissions": t.required_permissions,
            "default_timeout_seconds": t.default_timeout_seconds,
        })

    return json.dumps({
        "count": len(template_list),
        "workers": template_list,
    }, ensure_ascii=False)


def _tool_create_worker_template(args: dict[str, object], ctx: dict[str, object]) -> str:
    """Create a new worker template by writing worker.json to workspace."""
    from broodmind.store.models import WorkerTemplateRecord
    queen: Queen = ctx["queen"]
    base_dir: Path = ctx.get("base_dir", Path("workspace"))

    worker_id = str(args.get("id", "")).strip()
    name = str(args.get("name", "")).strip()
    description = str(args.get("description", "")).strip()
    system_prompt = str(args.get("system_prompt", "")).strip()

    if not worker_id:
        return "create_worker_template error: id is required."
    if not name:
        return "create_worker_template error: name is required."
    if not description:
        return "create_worker_template error: description is required."
    if not system_prompt:
        return "create_worker_template error: system_prompt is required."

    # Check if worker already exists
    existing = queen.store.get_worker_template(worker_id)
    if existing:
        return f"create_worker_template error: worker '{worker_id}' already exists. Use update_worker_template to modify it."

    # Get optional parameters with defaults
    available_tools = args.get("available_tools") if isinstance(args.get("available_tools"), list) else []
    required_permissions = args.get("required_permissions") if isinstance(args.get("required_permissions"), list) else []
    max_thinking_steps = int(args.get("max_thinking_steps")) if args.get("max_thinking_steps") else 10
    default_timeout_seconds = int(args.get("default_timeout_seconds")) if args.get("default_timeout_seconds") else 300

    # Build worker.json content
    worker_config = {
        "id": worker_id,
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "available_tools": available_tools,
        "required_permissions": required_permissions,
        "max_thinking_steps": max_thinking_steps,
        "default_timeout_seconds": default_timeout_seconds,
    }

    # Write worker.json file
    worker_dir = base_dir / "workers" / worker_id
    try:
        worker_dir.mkdir(parents=True, exist_ok=True)
        worker_file = worker_dir / "worker.json"
        worker_file.write_text(json.dumps(worker_config, indent=2), encoding="utf-8")
    except Exception as e:
        return f"create_worker_template error: failed to write worker.json: {e}"

    return json.dumps({
        "status": "created",
        "worker_id": worker_id,
        "name": name,
        "description": description,
        "available_tools": available_tools,
        "required_permissions": required_permissions,
        "message": f"Worker template '{name}' created successfully at workers/{worker_id}/worker.json"
    }, ensure_ascii=False)


def _tool_update_worker_template(args: dict[str, object], ctx: dict[str, object]) -> str:
    """Update an existing worker template by modifying its worker.json file."""
    from broodmind.store.models import WorkerTemplateRecord
    queen: Queen = ctx["queen"]
    base_dir: Path = ctx.get("base_dir", Path("workspace"))

    worker_id = str(args.get("id", "")).strip()
    if not worker_id:
        return "update_worker_template error: id is required."

    # Read existing worker.json
    worker_file = base_dir / "workers" / worker_id / "worker.json"
    if not worker_file.exists():
        return f"update_worker_template error: worker '{worker_id}' not found. Use create_worker_template to create it."

    try:
        existing_config = json.loads(worker_file.read_text(encoding="utf-8"))
    except Exception as e:
        return f"update_worker_template error: failed to read worker.json: {e}"

    # Update fields if provided
    if args.get("name"):
        existing_config["name"] = str(args.get("name")).strip()
    if args.get("description"):
        existing_config["description"] = str(args.get("description")).strip()
    if args.get("system_prompt"):
        existing_config["system_prompt"] = str(args.get("system_prompt")).strip()
    if isinstance(args.get("available_tools"), list):
        existing_config["available_tools"] = args.get("available_tools")
    if isinstance(args.get("required_permissions"), list):
        existing_config["required_permissions"] = args.get("required_permissions")
    if args.get("max_thinking_steps"):
        existing_config["max_thinking_steps"] = int(args.get("max_thinking_steps"))
    if args.get("default_timeout_seconds"):
        existing_config["default_timeout_seconds"] = int(args.get("default_timeout_seconds"))

    # Write updated worker.json
    try:
        worker_file.write_text(json.dumps(existing_config, indent=2), encoding="utf-8")
    except Exception as e:
        return f"update_worker_template error: failed to write worker.json: {e}"

    return json.dumps({
        "status": "updated",
        "worker_id": worker_id,
        "name": existing_config["name"],
        "description": existing_config["description"],
        "message": f"Worker template '{existing_config['name']}' updated successfully at workers/{worker_id}/worker.json"
    }, ensure_ascii=False)


def _tool_delete_worker_template(args: dict[str, object], ctx: dict[str, object]) -> str:
    """Delete a worker template by removing its directory."""
    import shutil
    queen: Queen = ctx["queen"]
    base_dir: Path = ctx.get("base_dir", Path("workspace"))

    worker_id = str(args.get("id", "")).strip()
    if not worker_id:
        return "delete_worker_template error: id is required."

    # Check if worker exists
    worker_dir = base_dir / "workers" / worker_id
    if not worker_dir.exists():
        return f"delete_worker_template error: worker '{worker_id}' not found."

    # Delete the directory
    try:
        shutil.rmtree(worker_dir)
    except Exception as e:
        return f"delete_worker_template error: failed to delete directory: {e}"

    return json.dumps({
        "status": "deleted",
        "worker_id": worker_id,
        "message": f"Worker template '{worker_id}' deleted successfully. Directory workers/{worker_id}/ has been removed."
    }, ensure_ascii=False)


def _tool_start_worker(args: dict[str, object], ctx: dict[str, object]) -> str:
    """Start a worker task with the specified worker template."""
    queen: Queen = ctx["queen"]
    chat_id = int(ctx.get("chat_id") or 0)

    worker_id = str(args.get("worker_id", "")).strip()
    task = str(args.get("task", "")).strip()
    inputs = args.get("inputs") if isinstance(args.get("inputs"), dict) else {}
    tools = args.get("tools") if isinstance(args.get("tools"), list) else None
    timeout_seconds = int(args.get("timeout_seconds")) if args.get("timeout_seconds") else None

    if not worker_id:
        return "start_worker error: worker_id is required. Use list_workers to see available workers."
    if not task:
        return "start_worker error: task is required."

    # Verify worker template exists
    template = queen.store.get_worker_template(worker_id)
    if not template:
        return f"start_worker error: worker '{worker_id}' not found. Use list_workers to see available workers."

    run_id = queen._start_worker_async(
        worker_id=worker_id,
        task=task,
        chat_id=chat_id,
        inputs=inputs,
        tools=tools,
        timeout_seconds=timeout_seconds,
    )
    return json.dumps({
        "status": "started",
        "worker_id": worker_id,
        "run_id": run_id,
        "message": f"Worker '{template.name}' started. Use get_worker_status to check progress."
    }, ensure_ascii=False)


def _tool_stop_worker(args: dict[str, object], ctx: dict[str, object]) -> str:
    queen: Queen = ctx["queen"]
    worker_id = str(args.get("worker_id", "")).strip()
    if not worker_id:
        return "stop_worker error: worker_id is required."
    stopped = queen.runtime.stop_worker(worker_id)
    return json.dumps({"status": "stopped" if stopped else "not_found", "worker_id": worker_id}, ensure_ascii=False)


def _tool_get_worker_status(args: dict[str, object], ctx: dict[str, object]) -> str:
    queen: Queen = ctx["queen"]
    worker_id = str(args.get("worker_id", "")).strip()
    if not worker_id:
        return "get_worker_status error: worker_id is required."

    worker = queen.store.get_worker(worker_id)
    if not worker:
        return json.dumps({
            "status": "not_found",
            "worker_id": worker_id,
            "message": "Worker not found. It may be from an old conversation or never existed."
        }, ensure_ascii=False)

    return json.dumps({
        "status": worker.status,
        "worker_id": worker.id,
        "task": worker.task,
        "created_at": worker.created_at.isoformat(),
        "updated_at": worker.updated_at.isoformat(),
        "summary": worker.summary,
        "error": worker.error,
    }, ensure_ascii=False)


def _tool_list_active_workers(args: dict[str, object], ctx: dict[str, object]) -> str:
    queen: Queen = ctx["queen"]
    older_than_minutes = int(args.get("older_than_minutes") or 10)

    workers = queen.store.get_active_workers(older_than_minutes=older_than_minutes)
    worker_list = []
    for w in workers:
        worker_list.append({
            "worker_id": w.id,
            "status": w.status,
            "task": w.task,
            "created_at": w.created_at.isoformat(),
            "updated_at": w.updated_at.isoformat(),
            "summary": w.summary,
            "error": w.error,
        })

    return json.dumps({
        "count": len(worker_list),
        "workers": worker_list,
    }, ensure_ascii=False)


def _tool_get_worker_result(args: dict[str, object], ctx: dict[str, object]) -> str:
    queen: Queen = ctx["queen"]
    worker_id = str(args.get("worker_id", "")).strip()
    if not worker_id:
        return "get_worker_result error: worker_id is required."

    worker = queen.store.get_worker(worker_id)
    if not worker:
        return json.dumps({
            "status": "not_found",
            "worker_id": worker_id,
            "message": "Worker not found."
        }, ensure_ascii=False)

    if worker.status == "completed":
        return json.dumps({
            "status": "completed",
            "worker_id": worker.id,
            "summary": worker.summary,
            "output": worker.output,
        }, ensure_ascii=False)
    elif worker.status == "failed":
        return json.dumps({
            "status": "failed",
            "worker_id": worker.id,
            "error": worker.error or "Unknown error",
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "status": worker.status,
            "worker_id": worker.id,
            "message": f"Worker is still {worker.status}. Result not available yet.",
        }, ensure_ascii=False)
