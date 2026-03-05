from __future__ import annotations

from fastapi.testclient import TestClient

from broodmind.config.settings import Settings
from broodmind.gateway.app import build_app


def test_dashboard_returns_legacy_html_when_webapp_flag_disabled(tmp_path) -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123:abc",
        BROODMIND_STATE_DIR=tmp_path / "state",
        BROODMIND_WORKSPACE_DIR=tmp_path / "workspace",
        BROODMIND_WEBAPP_ENABLED=False,
    )
    app = build_app(settings)
    client = TestClient(app)

    response = client.get("/dashboard")
    assert response.status_code == 503
    assert "Dashboard Is Unavailable" in response.text


def test_dashboard_serves_webapp_when_flag_enabled(tmp_path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text("<html><body>webapp-shell</body></html>", encoding="utf-8")
    (dist / "asset.js").write_text("console.log('ok');", encoding="utf-8")

    settings = Settings(
        TELEGRAM_BOT_TOKEN="123:abc",
        BROODMIND_STATE_DIR=tmp_path / "state",
        BROODMIND_WORKSPACE_DIR=tmp_path / "workspace",
        BROODMIND_WEBAPP_ENABLED=True,
        BROODMIND_WEBAPP_DIST_DIR=dist,
    )
    app = build_app(settings)
    client = TestClient(app)

    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "webapp-shell" in page.text

    asset = client.get("/dashboard/asset.js")
    assert asset.status_code == 200
    assert "console.log('ok')" in asset.text
