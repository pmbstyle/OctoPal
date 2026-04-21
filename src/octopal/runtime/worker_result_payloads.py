from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from octopal.runtime.tool_payloads import render_tool_result_for_llm


@dataclass(frozen=True)
class WorkerOutputContextBudget:
    inline_output_chars: int
    preview_chars: int
    max_available_keys: int = 200
    omit_telemetry_in_preview: bool = True


@dataclass(frozen=True)
class WorkerOutputContextPayload:
    output: Any
    output_truncated: bool
    output_preview_text: str
    available_keys: list[str]
    output_chars: int


ROUTE_WORKER_OUTPUT_CONTEXT_BUDGET = WorkerOutputContextBudget(
    inline_output_chars=64_000,
    preview_chars=48_000,
    max_available_keys=200,
)

SYNTHESIZE_WORKER_OUTPUT_CONTEXT_BUDGET = WorkerOutputContextBudget(
    inline_output_chars=6_000,
    preview_chars=2_500,
    max_available_keys=80,
)


def summarize_worker_output_for_context(
    output: Any,
    *,
    budget: WorkerOutputContextBudget,
) -> WorkerOutputContextPayload:
    if output is None:
        return WorkerOutputContextPayload(
            output=None,
            output_truncated=False,
            output_preview_text="",
            available_keys=[],
            output_chars=0,
        )

    serialized_output = json.dumps(output, ensure_ascii=False, default=str)
    output_chars = len(serialized_output)
    available_keys = list(output.keys()) if isinstance(output, dict) else []

    if output_chars <= budget.inline_output_chars:
        return WorkerOutputContextPayload(
            output=output,
            output_truncated=False,
            output_preview_text="",
            available_keys=available_keys,
            output_chars=output_chars,
        )

    preview_source = _preview_source_for_output(
        output,
        omit_telemetry=budget.omit_telemetry_in_preview,
    )
    output_summary: Any
    if isinstance(output, dict):
        output_summary = {"available_keys": available_keys[: budget.max_available_keys]}
    else:
        output_summary = {"output_type": type(output).__name__}

    return WorkerOutputContextPayload(
        output=output_summary,
        output_truncated=True,
        output_preview_text=render_tool_result_for_llm(
            preview_source,
            max_chars=budget.preview_chars,
        ).text,
        available_keys=available_keys,
        output_chars=output_chars,
    )


def _preview_source_for_output(output: Any, *, omit_telemetry: bool) -> Any:
    if not isinstance(output, dict) or not omit_telemetry:
        return output
    if "_telemetry" not in output or len(output) <= 1:
        return output
    return {key: value for key, value in output.items() if key != "_telemetry"}
