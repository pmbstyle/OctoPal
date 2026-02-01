from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import importlib
import importlib.util

from broodmind.workers.contracts import WorkerSpec


def main() -> None:
    spec_path = None
    if len(sys.argv) >= 2:
        spec_path = sys.argv[1]
    if not spec_path:
        spec_path = os.getenv("BROODMIND_WORKER_SPEC")
    if not spec_path:
        raise SystemExit("spec path required")

    spec_path = _resolve_spec_path(spec_path)
    spec = WorkerSpec.model_validate_json(Path(spec_path).read_text(encoding="utf-8"))
    if spec.worker_files:
        entry_path = Path.cwd() / spec.worker_entrypoint
        if not entry_path.exists():
            raise SystemExit(f"Worker entrypoint not found: {entry_path}")
        module = _load_module_from_path(entry_path)
        if not hasattr(module, "run_worker"):
            raise SystemExit(f"Worker entrypoint missing run_worker: {entry_path}")
        asyncio.run(module.run_worker(sys.argv[1]))
        return

    module = importlib.import_module(spec.worker_module)
    if not hasattr(module, "run_worker"):
        raise SystemExit(f"Worker module missing run_worker: {spec.worker_module}")
    asyncio.run(module.run_worker(sys.argv[1]))


def _load_module_from_path(path: Path):
    spec = importlib.util.spec_from_file_location("dynamic_worker", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Failed to load worker module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_spec_path(spec_path: str) -> str:
    candidate_paths = [spec_path]
    if not spec_path.startswith("/"):
        candidate_paths.append(f"/{spec_path}")
    for candidate in candidate_paths:
        if Path(candidate).exists():
            return candidate
    return spec_path


if __name__ == "__main__":
    main()
