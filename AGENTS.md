# Repository Guidelines

## Project Structure & Module Organization

- `src/broodmind/` holds the core Python package (CLI, gateway, workers, providers, and shared utilities).
- `docker/` contains container assets (worker image Dockerfile).
- `data/` is runtime state storage (SQLite DB, logs); avoid committing generated files.
- `workspace/` is the default worker workspace and scratch area.
- `README.md` covers quick start basics.

## Build, Test, and Development Commands

- `python -m venv .venv` and `pip install -e .` set up a local editable environment.
- `broodmind start` runs the Telegram bot and core services.
- `broodmind gateway` starts the FastAPI gateway on `BROODMIND_GATEWAY_HOST`/`BROODMIND_GATEWAY_PORT`.
- `broodmind status` shows health and last message timestamp.
- `broodmind logs --follow` tails `data/logs/broodmind.log`.
- `broodmind build-worker-image --tag broodmind-worker:latest` builds the Docker worker image.

## Coding Style & Naming Conventions

- Python code lives under `src/` with package imports rooted at `broodmind`.
- Use 4-space indentation and follow PEP 8 conventions (no repo-wide formatter is configured).
- Prefer descriptive module names (e.g., `gateway/`, `worker_sdk/`) and keep CLI commands in `cli/`.

## Testing Guidelines

- No test framework or test directory is configured yet.
- If you add tests, place them under `tests/` and use a consistent naming pattern like `test_<module>.py`.
- Document the new test command in this file and `README.md` when adding test tooling.

## Commit & Pull Request Guidelines

- Git history currently shows a single commit (`init`); no established convention yet.
- Use concise, imperative commit subjects (e.g., `add worker status command`).
- PRs should include: a short description, linked issue (if any), and screenshots/logs for user-facing changes.

## Security & Configuration Tips

- Copy `.env.example` to `.env` and keep secrets out of version control.
- Key settings include `TELEGRAM_BOT_TOKEN`, provider API keys, and `BROODMIND_STATE_DIR` paths.

## Queen Context Reset Policy

- The Queen can invoke `queen_context_reset` to compact/reset overloaded chat context.
- Preferred default is `mode=soft` with structured handoff fields (`goal_now`, `done`, `open_threads`, `critical_constraints`, `next_step`).
- Persist reset artifacts in workspace memory:
  - `memory/handoff.md`, `memory/handoff.json`
  - `memory/context-audit.md`, `memory/context-audit.jsonl`
- Confirmation is required when:
  - `mode=hard`
  - `confidence < 0.7`
  - repeated resets occur without progress (`N=2`)
- After reset, force a wake-up choice (`continue / clarify / replan`) before major actions.
