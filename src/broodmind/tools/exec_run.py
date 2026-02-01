from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def exec_run(args: dict[str, Any], base_dir: Path) -> str:
    command = str(args.get("command", "")).strip()
    if not command:
        return "exec_run error: command is required."
    timeout_seconds = int(args.get("timeout_seconds", 20) or 20)
    try:
        result = subprocess.run(
            command,
            cwd=str(base_dir),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        payload = {
            "returncode": result.returncode,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:4000],
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return f"exec_run error: {exc}"
