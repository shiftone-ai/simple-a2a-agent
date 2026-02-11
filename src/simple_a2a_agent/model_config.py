"""Model configuration from environment variables."""

import os

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise ValueError(f"{name} is required.")


def load_model_from_env() -> Model:
    """Build a pydantic-ai model instance from environment variables."""
    provider = _required_env("SIMPLE_A2A_PROVIDER").strip().lower()
    model_name = _required_env("SIMPLE_A2A_MODEL").strip()
    base_url = _required_env("SIMPLE_A2A_BASE_URL").strip()
    api_key = os.getenv("SIMPLE_A2A_API_KEY")

    if provider == "openai":
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(base_url=base_url, api_key=api_key),
        )

    if provider == "anthropic":
        if not api_key:
            raise ValueError("SIMPLE_A2A_API_KEY is required when SIMPLE_A2A_PROVIDER=anthropic.")
        return AnthropicModel(
            model_name,
            provider=AnthropicProvider(base_url=base_url, api_key=api_key),
        )

    raise ValueError("SIMPLE_A2A_PROVIDER must be one of: openai, anthropic.")
