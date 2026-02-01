from __future__ import annotations

from broodmind.tools.exec_run import exec_run
from broodmind.tools.filesystem import fs_read, fs_write
from broodmind.tools.registry import ToolSpec
from broodmind.tools.web_fetch import web_fetch
from broodmind.tools.web_search import web_search


def get_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="web_search",
            description="Search the web using Brave Search. Returns titles, URLs, and snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "count": {"type": "integer"},
                    "country": {"type": "string"},
                    "search_lang": {"type": "string"},
                    "ui_lang": {"type": "string"},
                    "freshness": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            permission="network",
            scope="worker",
            handler=lambda args, ctx: web_search(args),
        ),
        ToolSpec(
            name="web_fetch",
            description="Fetch a URL and return a text snippet.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            permission="network",
            scope="worker",
            handler=lambda args, ctx: web_fetch(args),
        ),
        ToolSpec(
            name="fs_read",
            description="Read a file from the worker workspace.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            permission="filesystem_read",
            scope="worker",
            handler=lambda args, ctx: fs_read(args, ctx["base_dir"]),
        ),
        ToolSpec(
            name="fs_write",
            description="Write a file to the worker workspace.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            permission="filesystem_write",
            scope="worker",
            handler=lambda args, ctx: fs_write(args, ctx["base_dir"]),
        ),
        ToolSpec(
            name="fs_read",
            description="Read a file from the queen workspace.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
            permission="filesystem_read",
            scope="queen",
            handler=lambda args, ctx: fs_read(args, ctx["base_dir"]),
        ),
        ToolSpec(
            name="fs_write",
            description="Write a file to the queen workspace.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            permission="filesystem_write",
            scope="queen",
            handler=lambda args, ctx: fs_write(args, ctx["base_dir"]),
        ),
        ToolSpec(
            name="exec_run",
            description="Run a shell command in the worker workspace.",
            parameters={
                "type": "object",
                "properties": {"command": {"type": "string"}, "timeout_seconds": {"type": "integer"}},
                "required": ["command"],
                "additionalProperties": False,
            },
            permission="exec",
            scope="worker",
            handler=lambda args, ctx: exec_run(args, ctx["base_dir"]),
        ),
    ]
