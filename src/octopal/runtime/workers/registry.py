from __future__ import annotations

from dataclasses import dataclass

from octopal.runtime.workers.contracts import Capability


@dataclass(frozen=True)
class WorkerTypeSpec:
    type: str
    module: str
    description: str
    default_capabilities: list[Capability]


WORKER_REGISTRY: dict[str, WorkerTypeSpec] = {
    "web_fetch": WorkerTypeSpec(
        type="web_fetch",
        module="octopal.runtime.workers.reference.web_fetch_worker",
        description="Fetch a URL and summarize the contents.",
        default_capabilities=[Capability(type="network", scope="*", read_only=True)],
    ),
}


def get_worker_type(worker_type: str) -> WorkerTypeSpec | None:
    return WORKER_REGISTRY.get(worker_type)
