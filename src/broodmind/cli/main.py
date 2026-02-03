from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

import typer

from broodmind.config.settings import Settings, load_settings
from broodmind.gateway.app import build_app
from broodmind.logging_config import configure_logging
from broodmind.state import is_pid_running, read_status, write_start_status
from broodmind.telegram.bot import run_bot

app = typer.Typer(add_completion=False)
workers_app = typer.Typer(add_completion=False)
audit_app = typer.Typer(add_completion=False)


def _init_logging(settings: Settings) -> None:
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    log_dir = settings.state_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(
        log_level=settings.log_level, 
        log_dir=log_dir, 
        debug_prompts=settings.debug_prompts
    )


@app.command()
def start() -> None:
    settings = load_settings()
    _init_logging(settings)
    write_start_status(settings)
    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        # Use standard logging here as structlog might be torn down
        logging.getLogger(__name__).info("Shutting down")


@app.command()
def status() -> None:
    config_ok = True
    settings: Settings | None = None
    error_text = None
    try:
        settings = load_settings()
    except Exception as exc:
        config_ok = False
        error_text = str(exc)

    if not settings:
        typer.echo("running: unknown")
        typer.echo(f"config_ok: {config_ok}")
        if error_text:
            typer.echo(f"config_error: {error_text}")
        return

    status_data = read_status(settings)
    pid = status_data.get("pid") if status_data else None
    running = is_pid_running(pid)
    last_message = status_data.get("last_message_at") if status_data else None

    typer.echo(f"running: {str(running).lower()}")
    typer.echo(f"config_ok: {config_ok}")
    typer.echo(f"last_message_at: {last_message or 'unknown'}")


@workers_app.command("list")
def workers_list() -> None:
    settings = load_settings()
    store = SQLiteStore(settings)
    workers = store.list_workers()
    if not workers:
        typer.echo("No workers found.")
        return
    for worker in workers:
        typer.echo(f"{worker.id} {worker.status} {worker.task}")


@audit_app.command("list")
def audit_list(limit: int = 50) -> None:
    settings = load_settings()
    store = SQLiteStore(settings)
    events = store.list_audit(limit=limit)
    if not events:
        typer.echo("No audit events found.")
        return
    for event in events:
        typer.echo(
            f"{event.id} {event.ts.isoformat()} {event.level} {event.event_type} {event.correlation_id or ''}"
        )


@audit_app.command("show")
def audit_show(event_id: str) -> None:
    settings = load_settings()
    store = SQLiteStore(settings)
    event = store.get_audit(event_id)
    if not event:
        typer.echo("Audit event not found.")
        raise typer.Exit(code=1)
    typer.echo(f"id: {event.id}")
    typer.echo(f"ts: {event.ts.isoformat()}")
    typer.echo(f"level: {event.level}")
    typer.echo(f"event_type: {event.event_type}")
    typer.echo(f"correlation_id: {event.correlation_id}")
    typer.echo(f"data: {event.data}")


@app.command()
def logs(follow: bool = typer.Option(False, "--follow", "-f")) -> None:
    settings = load_settings()
    log_path = settings.state_dir / "logs" / "broodmind.log"
    if not log_path.exists():
        typer.echo(f"Log file not found: {log_path}")
        raise typer.Exit(code=1)
    if not follow:
        typer.echo(log_path.read_text(encoding="utf-8"))
        return
    with log_path.open("r", encoding="utf-8") as handle:
        handle.seek(0, 2)
        while True:
            line = handle.readline()
            if line:
                typer.echo(line.rstrip("\n"))
            else:
                time.sleep(0.5)


@app.command()
def gateway() -> None:
    settings = load_settings()
    app_instance = build_app(settings)
    import uvicorn

    uvicorn.run(app_instance, host=settings.gateway_host, port=settings.gateway_port)


@app.command()
def build_worker_image(tag: str = "broodmind-worker:latest") -> None:
    settings = load_settings()
    project_root = Path(__file__).resolve().parents[3]
    dockerfile = project_root / "docker" / "Dockerfile"
    if not dockerfile.exists():
        typer.echo(f"Dockerfile not found: {dockerfile}")
        raise typer.Exit(code=1)
    cmd = [
        "docker",
        "build",
        "--target",
        "worker",
        "-t",
        tag,
        "-f",
        str(dockerfile),
        str(project_root),
    ]
    typer.echo("Running: " + " ".join(cmd))
    raise SystemExit(__import__("subprocess").call(cmd))


app.add_typer(workers_app, name="workers")
app.add_typer(audit_app, name="audit")


if __name__ == "__main__":
    app()
