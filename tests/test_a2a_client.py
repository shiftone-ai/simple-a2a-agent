"""Tests for A2A client helpers."""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest
from a2a.types import AgentCapabilities, AgentCard, Message, Task, TaskState, TaskStatus
from a2a.utils.message import new_agent_text_message

from simple_a2a_agent.a2a_client import (
    _build_client,
    discover_agents,
    parse_discovery_urls,
    send_text_to_agent,
)


class FakeClient:
    """Minimal fake A2A client for testing."""

    def __init__(self, events: list[tuple[Task, None] | Message]) -> None:
        self._events = events
        self.close = AsyncMock()

    async def send_message(self, _request: Message) -> AsyncIterator[tuple[Task, None] | Message]:
        for event in self._events:
            yield event


def _build_task(state: TaskState, text: str | None) -> Task:
    message = None if text is None else new_agent_text_message(text, "ctx-1", "task-1")
    return Task(id="task-1", context_id="ctx-1", status=TaskStatus(state=state, message=message))


@pytest.mark.anyio
async def test_send_text_to_agent_returns_completed_task_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _build_task(TaskState.completed, "hello from remote")
    fake_client = FakeClient(events=[(task, None)])

    async def fake_build_client(*args, **kwargs):
        return fake_client

    monkeypatch.setattr("simple_a2a_agent.a2a_client._build_client", fake_build_client)

    result = await send_text_to_agent("http://agent.example", "hello")

    assert result == "hello from remote"
    fake_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_send_text_to_agent_returns_direct_message(monkeypatch: pytest.MonkeyPatch) -> None:
    direct_message = new_agent_text_message("direct response", "ctx-1", "task-1")
    fake_client = FakeClient(events=[direct_message])

    async def fake_build_client(*args, **kwargs):
        return fake_client

    monkeypatch.setattr("simple_a2a_agent.a2a_client._build_client", fake_build_client)

    result = await send_text_to_agent("http://agent.example", "hello")

    assert result == "direct response"
    fake_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_send_text_to_agent_raises_on_failed_task(monkeypatch: pytest.MonkeyPatch) -> None:
    failed_task = _build_task(TaskState.failed, "remote failure")
    fake_client = FakeClient(events=[(failed_task, None)])

    async def fake_build_client(*args, **kwargs):
        return fake_client

    monkeypatch.setattr("simple_a2a_agent.a2a_client._build_client", fake_build_client)

    with pytest.raises(RuntimeError, match="remote failure"):
        await send_text_to_agent("http://agent.example", "hello")

    fake_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_send_text_to_agent_raises_on_failed_task_without_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_task = _build_task(TaskState.failed, None)
    fake_client = FakeClient(events=[(failed_task, None)])

    async def fake_build_client(*args, **kwargs):
        return fake_client

    monkeypatch.setattr("simple_a2a_agent.a2a_client._build_client", fake_build_client)

    with pytest.raises(RuntimeError, match="state=failed"):
        await send_text_to_agent("http://agent.example", "hello")

    fake_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_send_text_to_agent_raises_when_no_response(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = FakeClient(events=[])

    async def fake_build_client(*args, **kwargs):
        return fake_client

    monkeypatch.setattr("simple_a2a_agent.a2a_client._build_client", fake_build_client)

    with pytest.raises(RuntimeError, match="did not return"):
        await send_text_to_agent("http://agent.example", "hello")

    fake_client.close.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("agent_url", "text"),
    [
        ("", "hello"),
        ("   ", "hello"),
        ("http://agent.example", ""),
        ("http://agent.example", "   "),
    ],
)
async def test_send_text_to_agent_rejects_blank_input(agent_url: str, text: str) -> None:
    with pytest.raises(ValueError):
        await send_text_to_agent(agent_url, text)


@pytest.mark.anyio
async def test_build_client_prefers_explicit_agent_url(monkeypatch: pytest.MonkeyPatch) -> None:
    card = AgentCard(
        name="Remote Agent",
        description="test",
        url="http://localhost:8000",
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[],
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
    )
    captured: dict[str, str] = {}
    fake_client = object()

    async def fake_get_agent_card(_self):
        return card

    def fake_create(_self, provided_card: AgentCard):
        captured["url"] = provided_card.url
        return fake_client

    monkeypatch.setattr(
        "simple_a2a_agent.a2a_client.A2ACardResolver.get_agent_card",
        fake_get_agent_card,
    )
    monkeypatch.setattr("simple_a2a_agent.a2a_client.ClientFactory.create", fake_create)

    async with httpx.AsyncClient() as http_client:
        created_client = await _build_client("http://127.0.0.1:9000", http_client)

    assert created_client is fake_client
    assert captured["url"] == "http://127.0.0.1:9000"


def test_parse_discovery_urls_deduplicates_and_normalizes() -> None:
    urls = parse_discovery_urls(" http://127.0.0.1:8001/ ,http://127.0.0.1:8002,http://127.0.0.1:8001  ")

    assert urls == ("http://127.0.0.1:8001", "http://127.0.0.1:8002")


@pytest.mark.anyio
async def test_discover_agents_returns_successful_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_fetch(agent_url: str, _http_client: httpx.AsyncClient) -> AgentCard:
        calls.append(agent_url)
        if agent_url.endswith(":8001"):
            return AgentCard(
                name="Agent 1",
                description="one",
                url=agent_url,
                version="0.1.0",
                capabilities=AgentCapabilities(streaming=False),
                skills=[],
                default_input_modes=["text/plain"],
                default_output_modes=["text/plain"],
            )
        raise RuntimeError("offline")

    monkeypatch.setattr("simple_a2a_agent.a2a_client._fetch_agent_card", fake_fetch)

    discovered = await discover_agents(
        ("http://127.0.0.1:8001", "http://127.0.0.1:8002"),
        timeout=1.0,
    )

    assert calls == ["http://127.0.0.1:8001", "http://127.0.0.1:8002"]
    assert len(discovered) == 1
    assert discovered[0].url == "http://127.0.0.1:8001"
    assert discovered[0].name == "Agent 1"
