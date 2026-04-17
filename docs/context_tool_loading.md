# Octo Context And Tool Loading

This note describes how Octo now keeps prompt size under control without losing access to the full tool surface.

## Goals

- Keep the initial Octo prompt small and stable.
- Preserve access to the full tool registry through search and expansion.
- Keep bootstrap context complete while trimming tool-loading overhead elsewhere.
- Compact bulky tool outputs before they re-enter the next model turn.

## Initial Tool Loading

Octo no longer starts each turn with the full available tool set.

Instead, the router activates a smaller orchestration core first:

- context and scheduler tools
- worker lifecycle tools
- filesystem tools
- canon and runtime self-observation tools
- `tool_catalog_search`

The rest of the registry stays available in memory and can be activated later when Octo explicitly discovers it through `tool_catalog_search`.

This keeps the initial tool payload smaller while preserving capability coverage.

## Bootstrap Context

Workspace bootstrap files are still loaded from the same sources:

- `AGENTS.md`
- `USER.md`
- `HEARTBEAT.md`
- `MEMORY.md`
- `experiments/README.md`
- daily memory notes

Bootstrap files are injected in full so Octo always starts with the complete workspace instructions and current memory notes.

Prompt-size control is handled elsewhere, primarily through deferred tool loading and compacted tool results.

## Tool Result Compaction

Before a tool result is appended back into the conversation:

- large nested payloads are compacted
- top-level summaries are added for dict/list results
- file and path hints are preserved when present

This makes follow-up turns cheaper and easier for the model to navigate.

## Observability

Octo now logs:

- active tool count
- available tool count
- deferred tool count
- bootstrap file count
- bootstrap context total chars
- when a tool result had to be compacted

The goal is to understand prompt growth from structure-level metrics, not from full raw payload logging.

## Environment Flags

- `OCTOPAL_OCTO_DEFER_TOOL_LOADING`
  - default: `true`
  - when `false`, Octo falls back to the older count-budget behavior

- `OCTOPAL_OCTO_MAX_TOOL_COUNT`
  - upper bound for total active tools after budgeting

- `OCTOPAL_OCTO_MAX_INITIAL_TOOL_COUNT`
  - upper bound for the initial Octo core tool set before catalog-based expansion

## Expected Effect

These changes should reduce prompt size in three places:

1. fewer tool schemas in the first request
2. unchanged full bootstrap workspace payloads
3. smaller tool-result messages in iterative tool loops

The next recommended validation step is to compare before/after values in runtime logs for:

- `Octo tools fetched`
- `Octo system prompt`
- `Octo bootstrap files`
- provider request payload char counts
