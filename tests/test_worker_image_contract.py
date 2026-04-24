from __future__ import annotations

from pathlib import Path


def test_worker_image_installs_playwright_browsers_in_shared_path() -> None:
    dockerfile = Path(__file__).resolve().parents[1] / "docker" / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in text
    assert "playwright install chromium" in text
    assert "chmod -R a+rX /ms-playwright" in text
