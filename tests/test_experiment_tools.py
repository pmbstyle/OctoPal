from __future__ import annotations

import asyncio
import json
from pathlib import Path

from octopal.tools.memory.experiments import octo_experiment_log
from octopal.tools.tools import get_tools


def test_get_tools_includes_octo_experiment_log() -> None:
    names = {tool.name for tool in get_tools(mcp_manager=None)}
    assert "octo_experiment_log" in names


def test_octo_experiment_log_appends_jsonl_entry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    ctx = {"base_dir": workspace}

    result = asyncio.run(
        octo_experiment_log(
            {
                "problem": "Octo re-reads files before acting",
                "classification": "behavioral",
                "source": "deliberation_audit",
                "status": "observed",
                "evidence": ["same file opened twice", "no new question depended on it"],
                "notes": "candidate for small heuristic only",
            },
            ctx,
        )
    )

    results_path = workspace / "experiments" / "results.jsonl"
    readme_path = workspace / "experiments" / "README.md"

    assert "Experiment entry logged:" in result
    assert results_path.exists()
    assert readme_path.exists()

    lines = [line for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1

    payload = json.loads(lines[0])
    assert payload["classification"] == "behavioral"
    assert payload["source"] == "deliberation_audit"
    assert payload["status"] == "observed"
    assert payload["problem"] == "Octo re-reads files before acting"
    assert payload["evidence"] == ["same file opened twice", "no new question depended on it"]
