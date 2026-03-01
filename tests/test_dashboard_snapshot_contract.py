from __future__ import annotations

from broodmind.gateway.dashboard import (
    _build_kpis,
    _derive_overall_health,
    _estimate_control_latency_p95_ms,
)


def test_estimate_control_latency_p95_ms_from_request_ack_pairs() -> None:
    requests = [
        {"request_id": "a", "timestamp": "2026-03-01T00:00:00+00:00"},
        {"request_id": "b", "timestamp": "2026-03-01T00:00:10+00:00"},
        {"request_id": "c", "timestamp": "2026-03-01T00:00:20+00:00"},
    ]
    acks = [
        {"request_id": "a", "timestamp": "2026-03-01T00:00:01+00:00"},
        {"request_id": "b", "timestamp": "2026-03-01T00:00:12+00:00"},
        {"request_id": "c", "timestamp": "2026-03-01T00:00:26+00:00"},
    ]

    # Latency samples: [1000, 2000, 6000] -> p95 should land on 6000
    assert _estimate_control_latency_p95_ms(requests, acks) == 6000


def test_build_kpis_sets_expected_status_levels() -> None:
    kpis = _build_kpis(
        latency_p95_ms=2600,
        log_health={"error_rate_5m": 0.25, "error_count_5m": 3, "event_count_5m": 12},
        queue_depth=14,
        active_workers=0,
    )

    assert kpis["latency_ms_p95"]["status"] == "warning"
    assert kpis["error_rate_5m"]["status"] == "warning"
    assert kpis["queue_depth"]["status"] == "warning"
    assert kpis["active_workers"]["status"] == "warning"


def test_derive_overall_health_prioritizes_critical_reasons() -> None:
    services = [
        {"id": "gateway", "name": "Gateway", "status": "ok", "reason": "running"},
        {"id": "queen", "name": "Queen", "status": "warning", "reason": "queue pressure rising"},
    ]

    status, reasons = _derive_overall_health(
        services=services,
        failed_workers=7,
        control_pending=0,
        log_health={"error_rate_5m": 0.1, "event_count_5m": 10},
        system_running=True,
    )

    assert status == "critical"
    assert any("failed workers" in line for line in reasons)
