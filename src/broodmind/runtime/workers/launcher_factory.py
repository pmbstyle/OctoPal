from __future__ import annotations

from broodmind.infrastructure.config.settings import Settings
from broodmind.runtime.workers.launcher import DockerLauncher, SameEnvLauncher, WorkerLauncher


def build_launcher(settings: Settings) -> WorkerLauncher:
    if settings.worker_launcher == "docker":
        host_workspace = settings.worker_docker_host_workspace
        if not host_workspace:
            host_workspace = str(settings.workspace_dir.resolve())
        return DockerLauncher(
            image=settings.worker_docker_image,
            host_workspace=host_workspace,
            container_workspace=settings.worker_docker_workspace,
        )
    return SameEnvLauncher()
