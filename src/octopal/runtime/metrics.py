from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

_WRITE_LOCK = Lock()


def update_component_gauges(component: str, gauges: dict[str, Any]) -> None:
    """Persist lightweight runtime gauges for a component."""
    if not component:
        return

    path = _metrics_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with _WRITE_LOCK:
        payload: dict[str, Any] = {}
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}

        payload[component] = {
            **gauges,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _atomic_write_json(path, payload)


def read_metrics_snapshot(state_dir: Path | None = None) -> dict[str, Any]:
    path = _metrics_path(state_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _metrics_path(state_dir: Path | None = None) -> Path:
    base = state_dir if state_dir is not None else Path(os.getenv("OCTOPAL_STATE_DIR", "data"))
    return base / "runtime_metrics.json"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
