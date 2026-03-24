from __future__ import annotations

from octopal.cli.configure import _configure_llm
from octopal.infrastructure.config.models import OctopalConfig, LLMConfig


def test_configure_llm_quick_mode_allows_custom_base_url(monkeypatch) -> None:
    config = OctopalConfig()
    llm = LLMConfig(provider_id="openrouter")

    int_answers = iter([1])
    prompt_answers = iter(
        [
            "router-key",
            "anthropic/claude-sonnet-4",
            "https://custom.router/v1",
        ]
    )
    confirm_answers = iter([False])

    monkeypatch.setattr(
        "octopal.cli.configure.IntPrompt.ask",
        lambda *args, **kwargs: next(int_answers),
    )
    monkeypatch.setattr(
        "octopal.cli.configure.Prompt.ask",
        lambda *args, **kwargs: next(prompt_answers),
    )
    monkeypatch.setattr(
        "octopal.cli.configure.Confirm.ask",
        lambda *args, **kwargs: next(confirm_answers),
    )

    _configure_llm(config, "Worker (Default)", llm, advanced=False)

    assert llm.provider_id == "openrouter"
    assert llm.api_base == "https://custom.router/v1"


def test_configure_llm_quick_mode_can_keep_recommended_base_url(monkeypatch) -> None:
    config = OctopalConfig()
    llm = LLMConfig(provider_id="openrouter")

    int_answers = iter([1])
    prompt_answers = iter(
        [
            "router-key",
            "anthropic/claude-sonnet-4",
        ]
    )
    confirm_answers = iter([True])

    monkeypatch.setattr(
        "octopal.cli.configure.IntPrompt.ask",
        lambda *args, **kwargs: next(int_answers),
    )
    monkeypatch.setattr(
        "octopal.cli.configure.Prompt.ask",
        lambda *args, **kwargs: next(prompt_answers),
    )
    monkeypatch.setattr(
        "octopal.cli.configure.Confirm.ask",
        lambda *args, **kwargs: next(confirm_answers),
    )

    _configure_llm(config, "Octo", llm, advanced=False)

    assert llm.api_base == "https://openrouter.ai/api/v1"
