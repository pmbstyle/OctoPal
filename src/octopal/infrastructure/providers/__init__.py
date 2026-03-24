"""LLM providers for Octopal."""

from octopal.infrastructure.providers.base import InferenceProvider, Message
from octopal.infrastructure.providers.litellm_provider import LiteLLMProvider

__all__ = [
    "InferenceProvider",
    "Message",
    "LiteLLMProvider",
]
