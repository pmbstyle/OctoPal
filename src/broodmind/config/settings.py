from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    zai_api_key: str | None = Field(default=None, alias="ZAI_API_KEY")
    zai_base_url: str = Field("https://api.z.ai/api/coding/paas/v4", alias="ZAI_BASE_URL")
    zai_chat_path: str = Field("/chat/completions", alias="ZAI_CHAT_PATH")
    zai_timeout_seconds: float = Field(45.0, alias="ZAI_TIMEOUT_SECONDS")
    zai_connect_timeout_seconds: float = Field(15.0, alias="ZAI_CONNECT_TIMEOUT_SECONDS")
    zai_accept_language: str = Field("en-US,en", alias="ZAI_ACCEPT_LANGUAGE")
    zai_model: str = Field("glm-4.7", alias="ZAI_MODEL")

    brave_api_key: str | None = Field(default=None, alias="BRAVE_API_KEY")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_embed_model: str = Field(
        "text-embedding-3-small", alias="OPENAI_EMBED_MODEL"
    )

    log_level: str = Field("INFO", alias="BROODMIND_LOG_LEVEL")
    state_dir: Path = Field(Path("data"), alias="BROODMIND_STATE_DIR")
    workspace_dir: Path = Field(Path("workspace"), alias="BROODMIND_WORKSPACE_DIR")

    memory_top_k: int = Field(5, alias="BROODMIND_MEMORY_TOP_K")
    memory_min_score: float = Field(0.25, alias="BROODMIND_MEMORY_MIN_SCORE")
    memory_max_chars: int = Field(2000, alias="BROODMIND_MEMORY_MAX_CHARS")

    gateway_host: str = Field("0.0.0.0", alias="BROODMIND_GATEWAY_HOST")
    gateway_port: int = Field(8000, alias="BROODMIND_GATEWAY_PORT")

    worker_launcher: str = Field("same_env", alias="BROODMIND_WORKER_LAUNCHER")
    worker_docker_image: str = Field("broodmind-worker:latest", alias="BROODMIND_WORKER_DOCKER_IMAGE")
    worker_docker_workspace: str = Field("/workspace", alias="BROODMIND_WORKER_DOCKER_WORKSPACE")
    worker_docker_host_workspace: str | None = Field(
        default=None, alias="BROODMIND_WORKER_DOCKER_HOST_WORKSPACE"
    )


def load_settings() -> Settings:
    settings = Settings()
    if not settings.zai_api_key:
        import os

        legacy = os.getenv("Z_AI_API_KEY")
        if legacy:
            settings = settings.model_copy(update={"zai_api_key": legacy})
    return settings
