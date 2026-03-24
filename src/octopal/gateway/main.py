from __future__ import annotations

from octopal.gateway.app import build_app
from octopal.infrastructure.config.settings import load_settings

settings = load_settings()
app = build_app(settings)
