from __future__ import annotations

from broodmind.cli.configure import _apply_staged_changes, _stage_provider_model_prefix
from broodmind.infrastructure.config.manager import ConfigManager


def test_stage_provider_model_prefix_removes_stale_prefix_for_ollama(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("BROODMIND_LITELLM_MODEL_PREFIX=openrouter\n", encoding="utf-8")
    config = ConfigManager(env_path)
    staged: dict[str, str | None] = {}

    _stage_provider_model_prefix(
        config,
        staged,
        provider_id="ollama",
        supports_model_prefix_override=False,
        advanced_mode=False,
    )

    assert staged == {"BROODMIND_LITELLM_MODEL_PREFIX": None}


def test_apply_staged_changes_unsets_removed_prefix(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "BROODMIND_LITELLM_PROVIDER_ID=ollama\nBROODMIND_LITELLM_MODEL_PREFIX=openrouter\n",
        encoding="utf-8",
    )
    config = ConfigManager(env_path)

    _apply_staged_changes(config, {"BROODMIND_LITELLM_MODEL_PREFIX": None})

    contents = env_path.read_text(encoding="utf-8")
    assert "BROODMIND_LITELLM_PROVIDER_ID=ollama" in contents
    assert "BROODMIND_LITELLM_MODEL_PREFIX" not in contents
    assert config.get("BROODMIND_LITELLM_MODEL_PREFIX") is None
