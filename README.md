# BroodMind

BroodMind is an AI orchestration system built around a **Queen + Workers** model.

- **Queen** talks to the user, plans work, tracks context, and chooses tools.
- **Workers** run focused tasks with bounded permissions and time limits.

It is designed for long-running assistant workflows (Telegram-first), with memory, scheduling, and operational guardrails.

## What It Can Do

- Handle Telegram conversations with planning + execution flow
- Delegate tasks to specialized workers
- Run filesystem/web/exec tools under policy controls
- Keep persistent memory and canon files in `workspace/memory/canon/`
- Track context health and proactively reset context when overloaded
- Expose a private dashboard/gateway for ops visibility

## Quick Start

### 1. Prerequisites

- Python 3.12+
- `uv` (recommended)
- Telegram bot token from [@BotFather](https://t.me/botfather)
- At least one LLM API key:
  - `ZAI_API_KEY` (default LiteLLM path), or
  - `OPENROUTER_API_KEY` (OpenRouter provider)

Install `uv` if needed:

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Install

```bash
git clone <repo-url>
cd BroodMind
uv sync
```

Alternative without `uv`:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
pip install -e .
```

### 3. Configure

```bash
uv run broodmind configure
```

`configure` creates/updates `.env` and bootstraps workspace files if missing.

### 4. Start

```bash
# background mode
uv run broodmind start

# foreground mode
uv run broodmind start --foreground
```

### 5. Check Health

```bash
uv run broodmind status
uv run broodmind logs --follow
```

## Core Commands

```bash
# lifecycle
uv run broodmind start
uv run broodmind stop
uv run broodmind restart
uv run broodmind status
uv run broodmind logs --follow

# gateway/dashboard
uv run broodmind gateway
uv run broodmind dashboard
uv run broodmind dashboard --watch

# worker templates
uv run broodmind sync-worker-templates
uv run broodmind sync-worker-templates --overwrite

# memory maintenance
uv run broodmind memory stats
uv run broodmind memory cleanup --dry-run
```

## Configuration (Most Important)

Main config is loaded from `.env`.

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Telegram bot token |
| `ALLOWED_TELEGRAM_CHAT_IDS` | Recommended | Allowed chat IDs list |
| `BROODMIND_LLM_PROVIDER` | No | `litellm` (default) or `openrouter` |
| `ZAI_API_KEY` | Conditional | Required for LiteLLM default path |
| `OPENROUTER_API_KEY` | Conditional | Required for OpenRouter |
| `BROODMIND_WORKSPACE_DIR` | No | Workspace root (default `workspace`) |
| `BROODMIND_STATE_DIR` | No | Runtime state dir (default `data`) |
| `BROODMIND_DASHBOARD_TOKEN` | Recommended | Protect `/api/dashboard/*` |
| `BROODMIND_WEBAPP_ENABLED` | No | Serve new dashboard from built web app assets |
| `BROODMIND_WEBAPP_DIST_DIR` | No | Override web app dist path (default `webapp/dist`) |

Useful optional keys:

- `BRAVE_API_KEY` for `web_search`
- `FIRECRAWL_API_KEY` for richer `web_fetch`
- `OPENAI_API_KEY` for embedding-based semantic memory

Dashboard note:

- Legacy inline `/dashboard` UI was removed.
- Build frontend via `cd webapp && npm run build`.
- Enable dashboard serving with `BROODMIND_WEBAPP_ENABLED=true`.
- `broodmind start` now auto-builds webapp assets when needed (if the flag is enabled).

## Architecture (Simple View)

- `src/broodmind/queen/` - Queen logic (routing, context, orchestration)
- `src/broodmind/workers/` - worker runtime + contracts
- `src/broodmind/tools/` - tool registry and tool implementations
- `src/broodmind/memory/` - memory, canon, memchain
- `src/broodmind/telegram/` - bot transport layer
- `src/broodmind/gateway/` - dashboard and API endpoints

## Context Health and Reset

The Queen monitors context pressure and can invoke `queen_context_reset`.

- Preferred mode: `soft`
- `hard` reset requires explicit confirmation
- Reset writes handoff/audit artifacts to:
  - `workspace/memory/handoff.md`
  - `workspace/memory/handoff.json`
  - `workspace/memory/context-audit.md`
  - `workspace/memory/context-audit.jsonl`

Tunable thresholds:

- `BROODMIND_CONTEXT_WATCH_SIZE`
- `BROODMIND_CONTEXT_WATCH_REPETITION`
- `BROODMIND_CONTEXT_WATCH_ERROR_STREAK`
- `BROODMIND_CONTEXT_WATCH_NO_PROGRESS`
- `BROODMIND_CONTEXT_RESET_SOON_SIZE`
- `BROODMIND_CONTEXT_RESET_SOON_REPETITION`
- `BROODMIND_CONTEXT_RESET_SOON_ERROR_STREAK`
- `BROODMIND_CONTEXT_RESET_SOON_NO_PROGRESS`

## Optional: Docker Worker Launcher

Default runtime is non-Docker. If you want Dockerized workers:

```bash
uv run broodmind build-worker-image --tag broodmind-worker:latest
```

Then set in `.env`:

```env
BROODMIND_WORKER_LAUNCHER=docker
BROODMIND_WORKER_DOCKER_IMAGE=broodmind-worker:latest
```

Restart BroodMind after config changes.

## Development

```bash
uv sync --dev
uv run ruff check src tests
uv run pytest -q
```

## Troubleshooting

### Bot starts but does not reply

- Verify `TELEGRAM_BOT_TOKEN`
- Verify your chat ID is in `ALLOWED_TELEGRAM_CHAT_IDS`
- Check `uv run broodmind status` and `uv run broodmind logs --follow`

### LLM errors

- For LiteLLM path: set `ZAI_API_KEY`
- For OpenRouter path: set `BROODMIND_LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY`

### Web search/fetch issues

- Add `BRAVE_API_KEY` for `web_search`
- Add `FIRECRAWL_API_KEY` for richer page extraction

## License

MIT
