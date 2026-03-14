from __future__ import annotations

import json
from types import SimpleNamespace

from broodmind.runtime.state import write_start_status


def test_write_start_status_persists_active_channel(tmp_path) -> None:
    settings = SimpleNamespace(state_dir=tmp_path, user_channel="whatsapp")
    write_start_status(settings)

    payload = json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    assert payload["active_channel"] == "WhatsApp"
