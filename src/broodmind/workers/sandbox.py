from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoftSandbox:
    env_whitelist: list[str]

    def build_env(self, base_env: dict[str, str]) -> dict[str, str]:
        allowed = {}
        for key in self.env_whitelist:
            if key in base_env:
                allowed[key] = base_env[key]
        return allowed
