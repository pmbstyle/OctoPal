from __future__ import annotations

from dataclasses import replace

from broodmind.tools.metadata import ToolMetadata
from broodmind.tools.registry import ToolSpec

_TOOL_METADATA_BY_NAME: dict[str, ToolMetadata] = {
    "fs_list": ToolMetadata(
        category="filesystem",
        profile_tags=("coding", "ops"),
        capabilities=("read_workspace", "list_workspace"),
    ),
    "fs_read": ToolMetadata(
        category="filesystem",
        profile_tags=("coding", "research", "ops"),
        capabilities=("read_workspace",),
    ),
    "fs_write": ToolMetadata(
        category="filesystem",
        risk="guarded",
        profile_tags=("coding", "ops"),
        capabilities=("write_workspace",),
    ),
    "fs_move": ToolMetadata(
        category="filesystem",
        risk="guarded",
        profile_tags=("coding", "ops"),
        capabilities=("write_workspace",),
    ),
    "fs_delete": ToolMetadata(
        category="filesystem",
        risk="dangerous",
        profile_tags=("coding", "ops"),
        capabilities=("write_workspace", "delete_workspace"),
    ),
    "download_file": ToolMetadata(
        category="filesystem",
        risk="guarded",
        profile_tags=("coding", "research"),
        capabilities=("network_fetch", "write_workspace"),
    ),
    "web_search": ToolMetadata(
        category="web",
        profile_tags=("research", "minimal"),
        capabilities=("network_fetch", "search"),
    ),
    "web_fetch": ToolMetadata(
        category="web",
        profile_tags=("research",),
        capabilities=("network_fetch", "fetch"),
    ),
    "markdown_new_fetch": ToolMetadata(
        category="web",
        profile_tags=("research", "minimal"),
        capabilities=("network_fetch", "fetch"),
    ),
    "fetch_plan": ToolMetadata(
        category="web",
        profile_tags=("research",),
        capabilities=("network_fetch", "planning"),
    ),
    "run_llm_subtask": ToolMetadata(
        category="llm",
        profile_tags=("coding", "research"),
        capabilities=("llm_delegate",),
    ),
    "manage_canon": ToolMetadata(
        category="memory",
        risk="guarded",
        profile_tags=("research", "communication"),
        capabilities=("memory_read", "memory_write"),
    ),
    "search_canon": ToolMetadata(
        category="memory",
        profile_tags=("research", "communication", "minimal"),
        capabilities=("memory_read", "search"),
    ),
    "queen_context_health": ToolMetadata(
        category="runtime",
        profile_tags=("minimal", "ops"),
        capabilities=("self_observe",),
    ),
    "queen_context_reset": ToolMetadata(
        category="runtime",
        risk="guarded",
        profile_tags=("ops",),
        capabilities=("self_observe", "self_recover"),
    ),
    "queen_opportunity_scan": ToolMetadata(
        category="runtime",
        profile_tags=("ops", "research"),
        capabilities=("self_observe", "planning"),
    ),
    "queen_self_queue_add": ToolMetadata(
        category="runtime",
        risk="guarded",
        profile_tags=("ops", "communication"),
        capabilities=("self_queue_write",),
    ),
    "queen_self_queue_list": ToolMetadata(
        category="runtime",
        profile_tags=("ops", "communication"),
        capabilities=("self_queue_read",),
    ),
    "queen_self_queue_take": ToolMetadata(
        category="runtime",
        risk="guarded",
        profile_tags=("ops", "communication"),
        capabilities=("self_queue_write",),
    ),
    "queen_self_queue_update": ToolMetadata(
        category="runtime",
        risk="guarded",
        profile_tags=("ops", "communication"),
        capabilities=("self_queue_write",),
    ),
    "queen_experiment_log": ToolMetadata(
        category="memory",
        risk="guarded",
        profile_tags=("ops",),
        capabilities=("memory_write", "self_improve"),
    ),
    "list_workers": ToolMetadata(
        category="workers",
        profile_tags=("communication", "coding", "research"),
        capabilities=("worker_read",),
    ),
    "start_worker": ToolMetadata(
        category="workers",
        risk="guarded",
        profile_tags=("communication", "coding", "research"),
        capabilities=("worker_spawn",),
    ),
    "start_child_worker": ToolMetadata(
        category="workers",
        risk="guarded",
        profile_tags=("coding",),
        capabilities=("worker_spawn", "child_spawn"),
    ),
    "start_workers_parallel": ToolMetadata(
        category="workers",
        risk="guarded",
        profile_tags=("communication", "research", "coding"),
        capabilities=("worker_spawn", "parallel_spawn"),
    ),
    "stop_worker": ToolMetadata(
        category="workers",
        risk="dangerous",
        profile_tags=("ops",),
        capabilities=("worker_control",),
    ),
    "get_worker_status": ToolMetadata(
        category="workers",
        profile_tags=("communication", "ops"),
        capabilities=("worker_read",),
    ),
    "list_active_workers": ToolMetadata(
        category="workers",
        profile_tags=("communication", "ops"),
        capabilities=("worker_read",),
    ),
    "get_worker_result": ToolMetadata(
        category="workers",
        profile_tags=("communication", "coding", "research"),
        capabilities=("worker_read",),
    ),
    "get_worker_output_path": ToolMetadata(
        category="workers",
        profile_tags=("coding", "ops"),
        capabilities=("worker_read", "artifact_lookup"),
    ),
    "synthesize_worker_results": ToolMetadata(
        category="workers",
        profile_tags=("communication", "research"),
        capabilities=("worker_read", "synthesis"),
    ),
    "propose_knowledge": ToolMetadata(
        category="memory",
        risk="guarded",
        profile_tags=("communication",),
        capabilities=("memory_write", "knowledge_proposal"),
    ),
    "exec_run": ToolMetadata(
        category="ops",
        risk="dangerous",
        profile_tags=("coding", "ops"),
        capabilities=("shell_exec",),
    ),
    "service_health": ToolMetadata(
        category="ops",
        profile_tags=("ops",),
        capabilities=("service_read",),
    ),
    "service_logs": ToolMetadata(
        category="ops",
        profile_tags=("ops",),
        capabilities=("service_read", "log_read"),
    ),
    "process_inspect": ToolMetadata(
        category="ops",
        profile_tags=("ops",),
        capabilities=("process_read",),
    ),
    "self_control": ToolMetadata(
        category="ops",
        risk="guarded",
        profile_tags=("ops",),
        capabilities=("service_control",),
    ),
    "config_audit": ToolMetadata(
        category="ops",
        profile_tags=("ops",),
        capabilities=("config_read", "audit"),
    ),
    "secret_scan": ToolMetadata(
        category="ops",
        profile_tags=("ops",),
        capabilities=("audit", "security_scan"),
    ),
    "git_ops": ToolMetadata(
        category="ops",
        risk="dangerous",
        profile_tags=("coding", "ops"),
        capabilities=("git_read", "git_write"),
    ),
    "test_run": ToolMetadata(
        category="ops",
        risk="guarded",
        profile_tags=("coding", "ops"),
        capabilities=("test_exec",),
    ),
    "coverage_report": ToolMetadata(
        category="ops",
        profile_tags=("coding", "ops"),
        capabilities=("test_read", "reporting"),
    ),
    "artifact_collect": ToolMetadata(
        category="ops",
        profile_tags=("ops",),
        capabilities=("artifact_read",),
    ),
    "mcp_connect": ToolMetadata(
        category="mcp",
        risk="guarded",
        capabilities=("mcp_manage",),
        profile_tags=("ops",),
    ),
    "mcp_disconnect": ToolMetadata(
        category="mcp",
        risk="guarded",
        capabilities=("mcp_manage",),
        profile_tags=("ops",),
    ),
    "mcp_list": ToolMetadata(
        category="mcp",
        capabilities=("mcp_read",),
        profile_tags=("ops",),
    ),
    "mcp_status": ToolMetadata(
        category="mcp",
        capabilities=("mcp_read",),
        profile_tags=("ops",),
    ),
    "mcp_call": ToolMetadata(
        category="mcp",
        risk="guarded",
        capabilities=("mcp_exec",),
        profile_tags=("ops", "research", "coding"),
    ),
    "list_skills": ToolMetadata(
        category="skills",
        capabilities=("skill_read",),
        profile_tags=("ops",),
    ),
    "add_skill": ToolMetadata(
        category="skills",
        risk="guarded",
        capabilities=("skill_write",),
        profile_tags=("ops",),
    ),
    "remove_skill": ToolMetadata(
        category="skills",
        risk="guarded",
        capabilities=("skill_write",),
        profile_tags=("ops",),
    ),
}


def annotate_tool_specs(tools: list[ToolSpec]) -> list[ToolSpec]:
    annotated: list[ToolSpec] = []
    for spec in tools:
        desired = resolve_tool_metadata(spec.name, existing=spec.metadata)
        if desired == spec.metadata:
            annotated.append(spec)
            continue
        annotated.append(replace(spec, metadata=desired))
    return annotated


def resolve_tool_metadata(name: str, *, existing: ToolMetadata | None = None) -> ToolMetadata:
    normalized = str(name).strip().lower()
    if normalized in _TOOL_METADATA_BY_NAME:
        return _TOOL_METADATA_BY_NAME[normalized]
    if normalized.startswith("skill_"):
        return ToolMetadata(
            category="skills",
            owner="workspace",
            risk="guarded",
            profile_tags=("communication", "research", "coding"),
            capabilities=("skill_use",),
        )
    if normalized.startswith("mcp_"):
        return ToolMetadata(
            category="mcp",
            owner="mcp",
            risk="guarded",
            profile_tags=("research", "coding", "ops"),
            capabilities=("mcp_exec",),
        )
    if existing is not None:
        return existing
    return ToolMetadata()
