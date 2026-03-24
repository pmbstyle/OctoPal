from __future__ import annotations

import json

from fastapi.testclient import TestClient

from octopal.gateway.app import build_app
from octopal.infrastructure.config.settings import Settings
from octopal.infrastructure.store.models import WorkerRecord
from octopal.infrastructure.store.sqlite import SQLiteStore
from octopal.runtime.state import write_start_status
from octopal.utils import utc_now


def _make_client(tmp_path, *, token: str = "") -> TestClient:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123:abc",
        OCTOPAL_STATE_DIR=tmp_path / "state",
        OCTOPAL_WORKSPACE_DIR=tmp_path / "workspace",
        OCTOPAL_DASHBOARD_TOKEN=token,
    )
    app = build_app(settings)
    return TestClient(app)


def test_dashboard_v2_routes_return_contract_envelopes(tmp_path) -> None:
    client = _make_client(tmp_path)
    cases = [
        ("/api/dashboard/v2/overview", "dashboard.v2.overview"),
        ("/api/dashboard/v2/incidents", "dashboard.v2.incidents"),
        ("/api/dashboard/v2/octo", "dashboard.v2.octo"),
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
        headers={"x-octopal-token": "secret-token"},
    )
    assert authorized.status_code == 200
    assert authorized.json()["contract_version"] == "dashboard.v2.overview"


def test_dashboard_v2_stream_route_is_registered(tmp_path) -> None:
    client = _make_client(tmp_path)
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    payload = schema.json()
    assert "/api/dashboard/v2/stream" in payload.get("paths", {})


def test_dashboard_v2_workers_exposes_worker_result_details(tmp_path) -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123:abc",
        OCTOPAL_STATE_DIR=tmp_path / "state",
        OCTOPAL_WORKSPACE_DIR=tmp_path / "workspace",
    )
    app = build_app(settings)
    store = SQLiteStore(settings)
    now = utc_now()
    store.create_worker(
        WorkerRecord(
            id="worker-12345678",
            status="completed",
            task="Summarize latest sync",
            granted_caps=[],
            created_at=now,
            updated_at=now,
            summary="Sync finished successfully",
            output={"report": {"status": "ok", "items": 3}},
            tools_used=["web_search", "web_fetch"],
            template_name="Research Worker",
        )
    )
    app.state.dashboard_store = store
    client = TestClient(app)

    headers = {"x-octopal-token": settings.dashboard_token} if settings.dashboard_token else {}
    response = client.get("/api/dashboard/v2/workers", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    recent = payload["workers"]["recent"]
    assert len(recent) == 1
    assert recent[0]["summary"] == "Sync finished successfully"
    assert recent[0]["result_preview"] == "Sync finished successfully"
    assert recent[0]["output"] == {"report": {"status": "ok", "items": 3}}


def test_dashboard_v2_uses_whatsapp_metrics_for_active_channel(tmp_path) -> None:
    settings = Settings(
        TELEGRAM_BOT_TOKEN="123:abc",
        OCTOPAL_USER_CHANNEL="whatsapp",
        OCTOPAL_STATE_DIR=tmp_path / "state",
        OCTOPAL_WORKSPACE_DIR=tmp_path / "workspace",
    )
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    write_start_status(settings)
    (settings.state_dir / "runtime_metrics.json").write_text(
        json.dumps(
            {
                "telegram": {
                    "chat_queues": 0,
                    "send_tasks": 0,
                    "updated_at": "2026-03-01T00:00:00+00:00",
                },
                "whatsapp": {
                    "connected": 1,
                    "chat_mappings": 2,
                    "updated_at": utc_now().isoformat(),
                },
                "octo": {
                    "followup_queues": 0,
                    "internal_queues": 0,
                    "followup_tasks": 0,
                    "internal_tasks": 0,
                },
                "exec_run": {
                    "background_sessions_running": 0,
                    "background_sessions_total": 0,
                },
            }
        ),
        encoding="utf-8",
    )

    app = build_app(settings)
    client = TestClient(app)
    headers = {"x-octopal-token": settings.dashboard_token} if settings.dashboard_token else {}

    overview = client.get("/api/dashboard/v2/overview", headers=headers)
    assert overview.status_code == 200
    overview_payload = overview.json()
    assert overview_payload["health"]["status"] == "ok"
    assert "Telegram" not in overview_payload["health"]["summary"]
    assert all("Telegram:" not in reason for reason in overview_payload["health"]["reasons"])
    assert overview_payload["system"]["active_channel"] == "WhatsApp"
    assert overview_payload["system"]["active_channel_id"] == "whatsapp"

    octo = client.get("/api/dashboard/v2/octo", headers=headers)
    assert octo.status_code == 200
    octo_payload = octo.json()
    assert octo_payload["queues"]["active_channel"] == "whatsapp"
    assert octo_payload["queues"]["active_channel_label"] == "WhatsApp"
    assert octo_payload["queues"]["channel_connected"] == 1
    assert octo_payload["queues"]["channel_chat_mappings"] == 2
    assert octo_payload["queues"]["channel_queue_depth"] == 0
    assert octo_payload["queues"]["channel_send_tasks"] is None
