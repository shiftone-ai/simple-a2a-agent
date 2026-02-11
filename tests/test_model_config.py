"""Tests for model configuration loading from environment variables."""

import pytest
from pydantic_ai.models.openai import OpenAIChatModel

from simple_a2a_agent.model_config import load_model_from_env


def test_load_model_from_env_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMPLE_A2A_PROVIDER", "openai")
    monkeypatch.setenv("SIMPLE_A2A_MODEL", "qwen/qwen3-coder-next")
    monkeypatch.setenv("SIMPLE_A2A_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.delenv("SIMPLE_A2A_API_KEY", raising=False)

    model = load_model_from_env()

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "qwen/qwen3-coder-next"
    assert str(model._provider.client.base_url) == "http://127.0.0.1:1234/v1/"


def test_load_model_from_env_anthropic_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMPLE_A2A_PROVIDER", "anthropic")
    monkeypatch.setenv("SIMPLE_A2A_MODEL", "qwen/qwen3-coder-next")
    monkeypatch.setenv("SIMPLE_A2A_BASE_URL", "http://127.0.0.1:1234")
    monkeypatch.delenv("SIMPLE_A2A_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="SIMPLE_A2A_API_KEY"):
        load_model_from_env()


def test_load_model_from_env_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMPLE_A2A_PROVIDER", "invalid")
    monkeypatch.setenv("SIMPLE_A2A_MODEL", "qwen/qwen3-coder-next")
    monkeypatch.setenv("SIMPLE_A2A_BASE_URL", "http://127.0.0.1:1234")

    with pytest.raises(ValueError, match="SIMPLE_A2A_PROVIDER"):
        load_model_from_env()


@pytest.mark.parametrize(
    "missing_var",
    ["SIMPLE_A2A_PROVIDER", "SIMPLE_A2A_MODEL", "SIMPLE_A2A_BASE_URL"],
)
def test_load_model_from_env_requires_vars(monkeypatch: pytest.MonkeyPatch, missing_var: str) -> None:
    monkeypatch.setenv("SIMPLE_A2A_PROVIDER", "openai")
    monkeypatch.setenv("SIMPLE_A2A_MODEL", "qwen/qwen3-coder-next")
    monkeypatch.setenv("SIMPLE_A2A_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.delenv(missing_var, raising=False)

    with pytest.raises(ValueError, match=missing_var):
        load_model_from_env()
