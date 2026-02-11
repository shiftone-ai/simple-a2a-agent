"""A2A client helpers for talking to remote agents."""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

import httpx
from a2a.client import A2ACardResolver, Client, ClientConfig, ClientFactory
from a2a.types import AgentCard, Message, Part, Role, Task, TaskState, TextPart
from a2a.utils.message import get_message_text


@dataclass(frozen=True, slots=True)
class DiscoveredAgent:
    """Live agent information resolved from an Agent Card."""

    name: str
    url: str
    description: str


def _normalize_agent_url(agent_url: str) -> str:
    return agent_url.strip().rstrip("/")


def parse_discovery_urls(raw_urls: str | None) -> tuple[str, ...]:
    """Parse a comma-separated candidate URL list into normalized unique URLs."""
    if raw_urls is None:
        return ()

    deduplicated: list[str] = []
    seen: set[str] = set()
    for raw in raw_urls.split(","):
        normalized = _normalize_agent_url(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduplicated.append(normalized)
    return tuple(deduplicated)


def _build_user_message(text: str) -> Message:
    return Message(
        role=Role.user,
        parts=[Part(root=TextPart(text=text))],
        message_id=str(uuid4()),
    )


def _extract_task_message(task: Task) -> str:
    if task.status.message is None:
        return ""
    return get_message_text(task.status.message).strip()


async def _build_client(agent_url: str, http_client: httpx.AsyncClient) -> Client:
    resolver = A2ACardResolver(http_client, agent_url)
    card = await resolver.get_agent_card()

    # Prefer the caller-provided URL even when the remote card advertises a different host.
    normalized_target_url = agent_url.rstrip("/")
    if card.url.rstrip("/") != normalized_target_url:
        card = card.model_copy(update={"url": normalized_target_url})

    factory = ClientFactory(ClientConfig(streaming=False, httpx_client=http_client))
    return factory.create(card)


async def _fetch_agent_card(agent_url: str, http_client: httpx.AsyncClient) -> AgentCard:
    resolver = A2ACardResolver(http_client, agent_url)
    return await resolver.get_agent_card()


async def discover_agents(
    candidate_urls: Sequence[str],
    *,
    timeout: float = 5.0,
) -> tuple[DiscoveredAgent, ...]:
    """Return agents that can be resolved from candidate URLs."""
    normalized_candidates = parse_discovery_urls(",".join(candidate_urls))
    if not normalized_candidates:
        return ()

    discovered: list[DiscoveredAgent] = []
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        for candidate_url in normalized_candidates:
            try:
                card = await _fetch_agent_card(candidate_url, http_client)
            except Exception:
                continue

            name = card.name.strip() if card.name else candidate_url
            description = card.description.strip() if card.description else ""
            discovered.append(
                DiscoveredAgent(
                    name=name,
                    url=candidate_url,
                    description=description,
                )
            )

    return tuple(discovered)


async def send_text_to_agent(agent_url: str, text: str, timeout: float = 30.0) -> str:
    """Send a text message to a remote A2A agent and return its text response."""
    if not agent_url.strip():
        raise ValueError("agent_url must not be empty.")
    if not text.strip():
        raise ValueError("text must not be empty.")

    async with httpx.AsyncClient(timeout=timeout) as http_client:
        client = await _build_client(agent_url=agent_url, http_client=http_client)
        try:
            message = _build_user_message(text)
            async for event in client.send_message(message):
                if isinstance(event, Message):
                    return get_message_text(event).strip()

                task, _ = event
                response_text = _extract_task_message(task)

                if task.status.state == TaskState.completed:
                    return response_text
                if task.status.state in {TaskState.failed, TaskState.canceled}:
                    if response_text:
                        raise RuntimeError(response_text)
                    raise RuntimeError(f"Remote task ended with state={task.status.state.value}.")

            raise RuntimeError("Remote agent did not return a response.")
        finally:
            close_method = getattr(client, "close", None)
            if close_method is not None:
                await close_method()
