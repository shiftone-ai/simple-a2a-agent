"""Tests for autonomous peer discovery and outreach workflow."""

import pytest

from simple_a2a_agent.a2a_client import DiscoveredAgent
from simple_a2a_agent.autonomy import (
    AutonomousRequest,
    AutonomyConfig,
    encode_autonomous_request,
    maybe_handle_autonomous_request,
)


def _build_config(
    *,
    name: str = "Agent A",
    self_url: str | None = "http://127.0.0.1:8001",
    discovery_urls: tuple[str, ...] = (
        "http://127.0.0.1:8001",
        "http://127.0.0.1:8002",
    ),
    max_hops: int = 1,
    timeout: float = 5.0,
) -> AutonomyConfig:
    return AutonomyConfig(
        agent_name=name,
        self_url=self_url,
        discovery_urls=discovery_urls,
        max_hops=max_hops,
        timeout=timeout,
    )


@pytest.mark.anyio
async def test_maybe_handle_autonomous_request_returns_none_for_normal_message() -> None:
    async def fake_discover(*_args, **_kwargs):
        raise AssertionError("discover should not be called for regular chat")

    async def fake_send(*_args, **_kwargs):
        raise AssertionError("send should not be called for regular chat")

    result = await maybe_handle_autonomous_request(
        "hello",
        config=_build_config(),
        discover=fake_discover,
        send=fake_send,
    )

    assert result is None


@pytest.mark.anyio
async def test_maybe_handle_autonomous_request_requires_discovery_urls_for_human_trigger() -> None:
    async def fake_discover(*_args, **_kwargs):
        raise AssertionError("discover should not be called without discovery URLs")

    async def fake_send(*_args, **_kwargs):
        raise AssertionError("send should not be called without discovery URLs")

    result = await maybe_handle_autonomous_request(
        "他のagentに挨拶してみてください",
        config=_build_config(discovery_urls=()),
        discover=fake_discover,
        send=fake_send,
    )

    assert result is not None
    output_text, is_autonomous = result
    assert "SIMPLE_A2A_DISCOVERY_URLS" in output_text
    assert is_autonomous is True


@pytest.mark.anyio
async def test_maybe_handle_autonomous_request_discovers_and_contacts_peers() -> None:
    discovered = [
        DiscoveredAgent(name="Agent A", url="http://127.0.0.1:8001", description="self"),
        DiscoveredAgent(name="Agent B", url="http://127.0.0.1:8002", description="peer"),
    ]
    sent: dict[str, str] = {}

    async def fake_discover(*_args, **_kwargs):
        return discovered

    async def fake_send(agent_url: str, text: str, timeout: float = 30.0) -> str:
        sent["url"] = agent_url
        sent["text"] = text
        sent["timeout"] = str(timeout)
        return "こんにちは、Agent Bです。"

    result = await maybe_handle_autonomous_request(
        "他のagentに挨拶してみてください",
        config=_build_config(max_hops=1),
        discover=fake_discover,
        send=fake_send,
    )

    assert result is not None
    output_text, is_autonomous = result
    assert "detected agents: 2" in output_text
    assert "contacted peers: 1" in output_text
    assert "Agent B" in output_text
    assert "こんにちは、Agent Bです。" in output_text
    assert sent["url"] == "http://127.0.0.1:8002"

    # The sent text should be a conversation message, not an encoded request
    assert "こんにちは！" in sent["text"]
    assert "挨拶" in sent["text"]


@pytest.mark.anyio
async def test_maybe_handle_autonomous_request_stops_when_hops_exhausted() -> None:
    request = AutonomousRequest(
        objective="relay",
        origin_name="Agent A",
        origin_url="http://127.0.0.1:8001",
        remaining_hops=0,
        visited_urls=("http://127.0.0.1:8001",),
    )

    async def fake_discover(*_args, **_kwargs):
        return [
            DiscoveredAgent(name="Agent A", url="http://127.0.0.1:8001", description="self"),
            DiscoveredAgent(name="Agent B", url="http://127.0.0.1:8002", description="peer"),
        ]

    async def fake_send(*_args, **_kwargs):
        raise AssertionError("send should not be called when remaining_hops=0")

    result = await maybe_handle_autonomous_request(
        encode_autonomous_request(request),
        config=_build_config(max_hops=1),
        discover=fake_discover,
        send=fake_send,
    )

    assert result is not None
    output_text, is_autonomous = result
    assert "remaining_hops=0" in output_text
    assert "contacted peers: 0" in output_text
    assert is_autonomous is True
