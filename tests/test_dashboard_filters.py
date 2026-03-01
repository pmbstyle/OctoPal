from __future__ import annotations

from broodmind.config.settings import Settings
from broodmind.gateway.dashboard import (
    DashboardFilters,
    _build_filters,
    _normalize_log_entry,
)


def _settings(tmp_path):
    return Settings(
        TELEGRAM_BOT_TOKEN="123:abc",
        BROODMIND_STATE_DIR=tmp_path / "state",
        BROODMIND_WORKSPACE_DIR=tmp_path / "workspace",
    )


def test_build_filters_normalizes_unknown_values(tmp_path) -> None:
    settings = _settings(tmp_path)
    filters = _build_filters(settings, window_minutes=17, service="weird", environment="")
    assert filters.window_minutes == 60
    assert filters.service == "all"
    assert filters.environment == "all"


def test_normalize_log_entry_respects_service_filter() -> None:
    filters = DashboardFilters(window_minutes=60, service="telegram", environment="all")
    line = '{"timestamp":"2026-03-01T00:00:00+00:00","level":"info","event":"telegram message queued"}'
    entry = _normalize_log_entry(line, filters=filters)
    assert entry is not None
    assert entry["service"] == "telegram"

    blocked = _normalize_log_entry(
        '{"timestamp":"2026-03-01T00:00:00+00:00","level":"info","event":"queen loop tick"}',
        filters=filters,
    )
    assert blocked is None
