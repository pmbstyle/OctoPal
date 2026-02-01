from __future__ import annotations

import re

import httpx

from broodmind.worker_sdk.worker import Worker
from broodmind.workers.contracts import Evidence, WorkerResult


_URL_RE = re.compile(r"https?://\S+")


async def run_worker(spec_path: str) -> None:
    worker = Worker.from_spec_file(spec_path)
    url = _extract_url(worker.spec.task)
    if not url:
        await worker.complete(
            WorkerResult(
                summary="No URL found in task.",
                evidence=[],
            )
        )
        return

    try:
        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            response = await client.get(url)
        evidence = Evidence(type="http_response", content=response.text[:1000])
        await worker.complete(
            WorkerResult(
                summary=f"Fetched {url} with status {response.status_code}.",
                evidence=[evidence],
            )
        )
    except Exception as exc:
        await worker.complete(
            WorkerResult(
                summary=f"Failed to fetch {url}: {exc}",
                evidence=[],
                risk_flags=["http_request_failed"],
            )
        )


def _extract_url(text: str) -> str | None:
    match = _URL_RE.search(text)
    if not match:
        return None
    return match.group(0)
