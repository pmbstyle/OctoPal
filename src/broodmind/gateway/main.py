from __future__ import annotations

from broodmind.infrastructure.config.settings import load_settings
from broodmind.gateway.app import build_app

settings = load_settings()
app = build_app(settings)
