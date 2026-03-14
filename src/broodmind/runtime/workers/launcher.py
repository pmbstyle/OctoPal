from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Protocol


class WorkerLauncher(Protocol):
    async def launch(
        self,
        spec_path: str,
        cwd: str,
        env: dict[str, str],
    ) -> asyncio.subprocess.Process: ...


@dataclass
class SameEnvLauncher:
    entrypoint_module: str = "broodmind.runtime.workers.entrypoint"

    async def launch(
        self,
        spec_path: str,
        cwd: str,
        env: dict[str, str],
    ) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            self.entrypoint_module,
            spec_path,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )


@dataclass
class DockerLauncher:
    image: str
    host_workspace: str
    container_workspace: str = "/workspace"
    entrypoint_module: str = "broodmind.runtime.workers.entrypoint"

    async def launch(
        self,
        spec_path: str,
        cwd: str,
        env: dict[str, str],
    ) -> asyncio.subprocess.Process:
        worker_id = os.path.basename(cwd.rstrip(os.sep))
        container_ws = self.container_workspace
        if not container_ws.startswith("/"):
            container_ws = "/" + container_ws
        spec_in_container = f"{container_ws}/{worker_id}/spec.json"
        return await asyncio.create_subprocess_exec(
            "docker",
            "run",
            "--rm",
            "-i",
            "-v",
            f"{self.host_workspace}:{self.container_workspace}",
            "-w",
            f"{self.container_workspace}/{worker_id}",
            "-e",
            f"BROODMIND_WORKER_SPEC={spec_in_container}",
            self.image,
            "python",
            "-m",
            self.entrypoint_module,
            spec_in_container,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_filter_env(env),
        )


def _filter_env(env: dict[str, str]) -> dict[str, str]:
    # Docker env must be explicit; keep only a safe subset.
    allowed = {"PYTHONPATH"}
    return {key: value for key, value in env.items() if key in allowed}
