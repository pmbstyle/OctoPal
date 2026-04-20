# Observability Tracing Plan

This note turns the Langfuse observability discussion into an implementation plan for Octo and worker debugging.

The goal is not "more logs". The goal is a trace model that lets us answer, quickly and consistently:

- what Octo is doing right now
- why it chose that path
- where a worker stalled or failed
- whether a result was routed back correctly
- whether the failure belongs to provider, tool, policy, delivery, or orchestration

## Principles

- Keep the current `structlog` logs as the low-level ground truth.
- Add a separate tracing layer for request lifecycles and state transitions.
- Default to metadata-first capture.
- Make the tracing sink optional and disabled by default.
- Reuse existing identifiers (`correlation_id`, `worker run_id`, `lineage_id`) instead of creating a second identity model.

## Trace Model

### Session

- One conversation/thread.
- Format:
  - `chat:<chat_id>` for Telegram/internal chat
  - `ws:<chat_id>` for WebSocket sessions

### Root Trace

- One inbound turn or internally triggered turn.
- Root trace id should reuse the current `correlation_id`.
- Root trace starts when Octo accepts the message and ends when the user-visible reply is finalized or explicitly suppressed.

### Child Spans

- Routing
- Planner
- Provider calls
- Tool calls
- Worker dispatch
- Worker runtime
- Worker follow-up routing
- Channel delivery
- Context health/reset

### Cross-Cutting IDs

- `trace_id`: current trace
- `root_trace_id`: original user turn that spawned follow-up work
- `session_id`: conversation bucket
- `span_id`, `parent_span_id`
- `worker_run_id`
- `lineage_id`
- `parent_worker_id`
- `chat_id`

## Event Envelope

Every trace/span event should support the same minimal envelope:

```json
{
  "timestamp": "2026-04-20T16:10:22Z",
  "trace_id": "turn-123",
  "root_trace_id": "turn-123",
  "session_id": "chat:42",
  "span_id": "span-456",
  "parent_span_id": "span-100",
  "event_name": "llm.call",
  "status": "ok",
  "duration_ms": 842,
  "chat_id": 42,
  "worker_run_id": null,
  "lineage_id": null,
  "attrs": {}
}
```

## Proposed TraceSink API

The tracing layer should be isolated behind a tiny interface so we can start with a no-op sink and later bind it to Langfuse.

```python
from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    root_trace_id: str
    session_id: str
    span_id: str
    parent_span_id: str | None = None
    chat_id: int | None = None
    worker_run_id: str | None = None
    lineage_id: str | None = None


class TraceSink(Protocol):
    async def start_trace(
        self,
        *,
        name: str,
        trace_id: str,
        root_trace_id: str,
        session_id: str,
        chat_id: int | None,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext: ...

    async def start_span(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> TraceContext: ...

    async def annotate(
        self,
        ctx: TraceContext,
        *,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    async def finish_span(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...

    async def finish_trace(
        self,
        ctx: TraceContext,
        *,
        status: str = "ok",
        output: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None: ...
```

## First Concrete Types

Implementation should begin with three classes:

- `NoopTraceSink`
  - default implementation
  - used when tracing is disabled or not configured
- `BufferedTraceHelpers`
  - small helper layer for timing, preview generation, hashing, and masking
- `LangfuseTraceSink`
  - actual backend adapter
  - should contain all Langfuse-specific code so the rest of the app stays backend-agnostic

## Capture Policy

The default policy should optimize for debuggability without leaking sensitive content.

### Default

- capture metadata
- capture short previews
- capture hashes of large content
- mask secrets and tokens
- do not capture full prompts or full tool results

### Optional Debug Capture

Enable only by explicit config flag or sampling:

- full prompt bodies
- full provider responses
- full tool args/results
- full worker summaries

### Suggested Helpers

- `preview_text(value: str, limit: int = 240) -> str`
- `hash_payload(value: Any) -> str`
- `mask_secrets(value: str) -> str`
- `summarize_exception(exc: Exception) -> dict[str, str]`

## Event Catalog

### `octo.turn`

Created for every inbound or internal turn.

Required attrs:

- `channel`
- `message_kind`
- `text_len`
- `has_images`
- `has_files`
- `internal_followup`
- `active_workers_count`
- `queued_followups_count`

### `octo.routing`

Required attrs:

- `route_mode`
- `provider_id`
- `model`
- `active_tool_count`
- `available_tool_count`
- `deferred_tool_count`
- `memory_hits`
- `bootstrap_context_len`
- `saved_file_paths_count`

### `octo.planner`

Required attrs:

- `planner_mode`
- `steps_count`
- `steps_preview`
- `failed`

### `llm.call`

Required attrs:

- `provider_id`
- `model`
- `call_type`
- `messages_count`
- `input_chars`
- `output_chars`
- `tool_count`
- `tool_names`
- `retry_count`
- `rate_limited`
- `finish_reason`
- `usage_input_tokens`
- `usage_output_tokens`
- `response_format_mode`
- `error_type`

### `octo.tool`

Required attrs:

- `tool_name`
- `args_hash`
- `args_preview`
- `result_size`
- `result_preview`
- `timed_out`
- `had_error`
- `policy_blocked`
- `loop_detector_level`

### `worker.dispatch`

Required attrs:

- `worker_template_id`
- `worker_run_id`
- `task_id`
- `task_preview`
- `timeout_seconds`
- `notify_user_policy`
- `allowed_paths_count`
- `spawn_reason`

### `worker.run`

Required attrs:

- `worker_run_id`
- `template_id`
- `template_name`
- `status`
- `tools_allowed`
- `tools_used`
- `summary_len`
- `questions_count`
- `artifacts_count`
- `has_blocking_failure`
- `recovery_attempts`

### `worker.followup`

Required attrs:

- `worker_run_id`
- `followup_mode`
- `batch_size`
- `routing_timeout`
- `followup_required`
- `notify_user_policy_resolved`
- `user_visible`
- `message_len`

### `channel.delivery`

Required attrs:

- `delivery_channel`
- `delivery_mode`
- `attempted`
- `succeeded`
- `suppressed_reason`
- `control_response`
- `message_len`
- `error_type`

### `context.health`

Required attrs:

- `context_size_estimate`
- `repetition_score`
- `error_streak`
- `no_progress_turns`
- `resets_since_progress`
- `state`

### `context.reset`

Required attrs:

- `mode`
- `confidence`
- `requires_confirmation`
- `reasons`
- `handoff_written`
- `reflection_written`
- `memchain_written`

### Point Events

- `octo.tool_loop_detected`
- `octo.policy_blocked`
- `provider.transient_retry`
- `provider.rate_limited`
- `worker.progress_emitted`
- `worker.child_batch_resumed`
- `delivery.suppressed`
- `context.reset_requested`
- `context.reset_completed`
- `system.error`

## File-Level Hook Plan

### 1. Logging / sink setup

Create:

- `src/octopal/infrastructure/observability/__init__.py`
- `src/octopal/infrastructure/observability/base.py`
- `src/octopal/infrastructure/observability/noop.py`
- `src/octopal/infrastructure/observability/helpers.py`
- `src/octopal/infrastructure/observability/langfuse_sink.py`

Touch:

- `src/octopal/infrastructure/config/models.py`
- `src/octopal/infrastructure/config/settings.py`
- `src/octopal/infrastructure/logging.py`

Responsibilities:

- observability config model
- environment-driven enable/disable
- sink factory
- capture policy helpers

### 2. Octo turn lifecycle

Touch:

- `src/octopal/runtime/octo/core.py`

Add hooks for:

- turn start
- turn end
- worker dispatch
- worker completion/failure
- follow-up routing
- delivery result
- context health snapshots
- context reset completion

### 3. Routing and tool loop

Touch:

- `src/octopal/runtime/octo/router.py`

Add hooks for:

- routing span
- planner span
- verifier span if retained
- tool-call spans
- tool loop events
- policy block events
- tool catalog expansion events

### 4. Provider instrumentation

Touch:

- `src/octopal/infrastructure/providers/litellm_provider.py`
- `src/octopal/infrastructure/providers/openrouter_provider.py`

Add hooks for:

- provider call spans
- retry/rate-limit events
- final usage and finish reason
- response_format downgrade annotations

### 5. Worker runtime lifecycle

Touch:

- `src/octopal/runtime/workers/runtime.py`
- optionally `src/octopal/runtime/workers/agent_worker.py`

Add hooks for:

- worker spawn
- worker process started
- worker approval flow
- worker result parsed
- worker failed
- child batch resume
- MCP worker bridge failures

### 6. Delivery and channel specifics

Touch:

- `src/octopal/channels/telegram/handlers.py`
- `src/octopal/gateway/ws.py` if needed

Add hooks for:

- delivery attempts
- suppressed sends
- send failures
- typing/reaction failures only if they are user-visible or repeatedly harmful

## Rollout Phases

### Phase 1: Foundation

- Add config and no-op sink
- Add helper functions for preview, hashing, masking
- Wire sink into Octo and WorkerRuntime constructors
- No backend dependency yet

Acceptance:

- app runs unchanged when tracing is disabled
- trace helper calls are safe and cheap

### Phase 2: Core turn tracing

- Instrument `octo.turn`
- Instrument `octo.routing`
- Instrument `llm.call`

Acceptance:

- one user turn produces a readable trace tree
- failures in provider calls are attached to the right trace

### Phase 3: Tool tracing

- Instrument `octo.tool`
- Add `octo.tool_loop_detected`
- Add `octo.policy_blocked`

Acceptance:

- a single bad tool loop is diagnosable from one trace

### Phase 4: Worker tracing

- Instrument `worker.dispatch`
- Instrument `worker.run`
- Instrument `worker.followup`

Acceptance:

- any completed or stuck worker can be tied back to its parent turn

### Phase 5: Delivery and context health

- Instrument `channel.delivery`
- Instrument `context.health`
- Instrument `context.reset`

Acceptance:

- "user got nothing" cases become distinguishable:
  - no reply generated
  - reply suppressed
  - delivery failed
  - worker follow-up timed out

### Phase 6: Langfuse backend

- Implement `LangfuseTraceSink`
- keep it behind config flag
- verify ingestion cost before enabling broad content capture

Acceptance:

- tracing can be turned on without changing business logic
- no raw secret leakage in captured metadata

## Minimal Config Proposal

Suggested settings:

- `observability_enabled: bool = False`
- `observability_backend: Literal["noop", "langfuse"] = "noop"`
- `observability_capture_content: bool = False`
- `observability_preview_chars: int = 240`
- `observability_sample_rate: float = 1.0`
- `langfuse_public_key: str | None = None`
- `langfuse_secret_key: str | None = None`
- `langfuse_host: str | None = None`

## Suggested First PR Breakdown

### PR 1

- config
- `TraceSink` interface
- `NoopTraceSink`
- helpers

### PR 2

- Octo turn/routing/provider instrumentation

### PR 3

- tool tracing and loop/policy events

### PR 4

- worker tracing and follow-up spans

### PR 5

- Langfuse backend adapter

## Debugging Queries This Plan Should Unlock

After rollout, we should be able to answer these questions from one trace:

- Why did Octo choose tools instead of replying directly?
- Which provider call failed, and after how many retries?
- Which tool call looped, with the same args or the same result?
- Which worker was started, from which parent turn, and with what timeout?
- Did the worker finish, fail, or time out during follow-up routing?
- Was the final user-visible reply generated but suppressed?
- Was context degradation already visible before the bad turn?

## Recommended Next Step

Implementation should start with Phase 1 and Phase 2 only.

That gives us a stable interface and immediate debugging value without committing the codebase to Langfuse-specific assumptions too early.
