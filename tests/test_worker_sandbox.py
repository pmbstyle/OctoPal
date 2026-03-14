from __future__ import annotations

from broodmind.runtime.workers.sandbox import SoftSandbox


def test_soft_sandbox_build_env_keeps_only_whitelisted_keys_in_order() -> None:
    sandbox = SoftSandbox(env_whitelist=["API_KEY", "HOME", "MISSING", "PATH"])

    result = sandbox.build_env(
        {
            "PATH": "/usr/bin",
            "HOME": "/home/broodmind",
            "SECRET": "nope",
            "API_KEY": "token",
        }
    )

    assert result == {
        "API_KEY": "token",
        "HOME": "/home/broodmind",
        "PATH": "/usr/bin",
    }


def test_soft_sandbox_build_env_returns_empty_when_no_keys_match() -> None:
    sandbox = SoftSandbox(env_whitelist=["OPENAI_API_KEY"])

    assert sandbox.build_env({"PATH": "/usr/bin"}) == {}
