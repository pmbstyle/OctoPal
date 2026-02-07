# Telegram Bot Features

This document describes the Telegram UX features currently implemented in BroodMind.

## Commands

The bot now supports explicit slash commands:

- `/help`
  - Shows available bot commands.
- `/status`
  - Shows bot/runtime status, PID, last heartbeat, and active/recent worker count.
- `/workers`
  - Shows discovered worker templates and recent workers.
- `/memory [limit]`
  - Shows a memory snapshot summary (total entries, unique chats, role distribution).
  - Optional `limit` is clamped to `50..1000` (default `300`).

If a message is not a slash command, it follows the normal Queen message flow.

## Progress Updates

The Queen emits progress milestones for worker launches and execution:

- `queued`
- `running`
- `completed`
- `failed`
- `duplicate`
- `worker_started`

Telegram receives these as lightweight progress messages. Repeated progress states are coalesced per chat for a short interval to reduce spam.

## Inline Worker Controls

When a worker starts, Telegram posts a control panel with inline buttons:

- `Refresh`
  - Fetches and shows the latest worker status.
- `Get result`
  - Fetches completed/failed result details.
- `Stop`
  - Stops a running worker.

## Callback Guardrails

Worker callback actions include safety checks:

- Callback payload format validation.
- Worker ID regex validation.
- Lock-safe execution under per-chat lock.
- Graceful handling for stale/cleaned-up workers (shows alert and removes outdated controls).
- State-aware controls: `Stop` is disabled when worker is no longer running.

## Notes

- All bot responses still use the existing queued sender path for ordered delivery.
- Existing approval callbacks (`approve:*`, `deny:*`) remain supported.
