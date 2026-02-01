from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from broodmind.intents.types import ActionIntent
from broodmind.policy.capabilities import DEFAULT_CAPABILITY_WHITELIST
from broodmind.policy.permits import ApprovalRequirement
from broodmind.workers.contracts import Capability


@dataclass
class PolicyEngine:
    whitelist: dict[str, list[str]] = None

    def __post_init__(self) -> None:
        if self.whitelist is None:
            self.whitelist = DEFAULT_CAPABILITY_WHITELIST

    def grant_capabilities(self, requested: list[Capability]) -> list[Capability]:
        granted: list[Capability] = []
        for cap in requested:
            allowed_scopes = self.whitelist.get(cap.type, [])
            if not allowed_scopes:
                continue
            if _scope_allowed(cap.scope, allowed_scopes):
                granted.append(cap)
        return granted

    def check_intent(self, intent: ActionIntent) -> ApprovalRequirement:
        if intent.requires_approval or intent.risk in {"high", "critical"}:
            return ApprovalRequirement(
                requires_approval=True,
                reason=f"risk={intent.risk}",
            )
        return ApprovalRequirement(requires_approval=False)


def _scope_allowed(scope: str, allowed_scopes: list[str]) -> bool:
    for allowed in allowed_scopes:
        if allowed == "*":
            return True
        if fnmatch.fnmatch(scope, allowed):
            return True
    return False
