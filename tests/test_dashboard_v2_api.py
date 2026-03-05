from __future__ import annotations

from fastapi.testclient import TestClient

from broodmind.config.settings import Settings
from broodmind.gateway.app import build_app


def _make_client(tmp_path, *, token: str = "") -> TestClient:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123:abc",
        BROODMIND_STATE_DIR=tmp_path / "state",
        BROODMIND_WORKSPACE_DIR=tmp_path / "workspace",
        BROODMIND_DASHBOARD_TOKEN=token,
    )
    app = build_app(settings)
    return TestClient(app)


def test_dashboard_v2_routes_return_contract_envelopes(tmp_path) -> None:
    client = _make_client(tmp_path)
    cases = [
        ("/api/dashboard/v2/overview", "dashboard.v2.overview"),
        ("/api/dashboard/v2/incidents", "dashboard.v2.incidents"),
        ("/api/dashboard/v2/queen", "dashboard.v2.queen"),
        ("/api/dashboard/v2/workers", "dashboard.v2.workers"),
        ("/api/dashboard/v2/system", "dashboard.v2.system"),
        ("/api/dashboard/v2/actions", "dashboard.v2.actions"),
    ]

    for route, version in cases:
        response = client.get(route)
        assert response.status_code == 200
        payload = response.json()
        assert payload["contract_version"] == version
        assert "generated_at" in payload
        assert "filters" in payload


def test_dashboard_v2_routes_require_token_when_configured(tmp_path) -> None:
    client = _make_client(tmp_path, token="secret-token")

    unauthorized = client.get("/api/dashboard/v2/overview")
    assert unauthorized.status_code == 401

    authorized = client.get(
        "/api/dashboard/v2/overview",
        headers={"x-broodmind-token": "secret-token"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["contract_version"] == "dashboard.v2.overview"


def test_dashboard_v2_stream_route_is_registered(tmp_path) -> None:
    client = _make_client(tmp_path)
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    payload = schema.json()
    assert "/api/dashboard/v2/stream" in payload.get("paths", {})
