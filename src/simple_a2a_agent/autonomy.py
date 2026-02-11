"""Autonomous peer discovery and outreach orchestration."""

import json
import logging
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from uuid import uuid4

from simple_a2a_agent.a2a_client import (
    DiscoveredAgent,
    discover_agents,
    parse_discovery_urls,
    send_text_to_agent,
)

AUTONOMOUS_REQUEST_PREFIX = "A2A_AUTONOMY::"
MAX_RESPONSE_PREVIEW_LINES = 6
MAX_RESPONSE_PREVIEW_CHARS = 1_200

logger = logging.getLogger("uvicorn.error")

DiscoverFn = Callable[..., Awaitable[Sequence[DiscoveredAgent]]]
SendFn = Callable[..., Awaitable[str]]
PeerResponseCallback = Callable[[DiscoveredAgent, str | None, Exception | None], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class AutonomyConfig:
    """Runtime configuration for autonomous peer outreach."""

    agent_name: str
    self_url: str | None
    discovery_urls: tuple[str, ...]
    max_hops: int
    timeout: float


@dataclass(frozen=True, slots=True)
class AutonomousRequest:
    """Serialized request payload used for agent-to-agent relay."""

    objective: str
    origin_name: str
    origin_url: str
    remaining_hops: int
    visited_urls: tuple[str, ...]
    relay_id: str = ""


def _normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


def _parse_non_negative_int(raw_value: str | None, *, default: int) -> int:
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        return default
    return max(parsed, 0)


def _parse_positive_float(raw_value: str | None, *, default: float) -> float:
    if raw_value is None:
        return default
    try:
        parsed = float(raw_value.strip())
    except ValueError:
        return default
    if parsed <= 0:
        return default
    return parsed


def _resolve_default_self_url_from_env(
    *, host_override: str | None = None, port_override: int | None = None
) -> str | None:
    host = host_override if host_override is not None else os.getenv("A2A_HOST", "127.0.0.1").strip()
    port = str(port_override) if port_override is not None else os.getenv("A2A_PORT", "8000").strip()
    if not host or not port:
        return None

    normalized_host = host
    if host in {"0.0.0.0", "::"}:
        normalized_host = "127.0.0.1"
    return f"http://{normalized_host}:{port}"


def load_autonomy_config_from_env(*, host: str | None = None, port: int | None = None) -> AutonomyConfig:
    """Load autonomous workflow config from environment variables."""
    agent_name = os.getenv("SIMPLE_A2A_AGENT_NAME", "Simple Agent").strip() or "Simple Agent"
    self_url = _normalize_url(os.getenv("SIMPLE_A2A_SELF_URL")) or _normalize_url(
        _resolve_default_self_url_from_env(host_override=host, port_override=port)
    )
    discovery_urls = parse_discovery_urls(os.getenv("SIMPLE_A2A_DISCOVERY_URLS"))
    max_hops = _parse_non_negative_int(os.getenv("SIMPLE_A2A_AUTONOMOUS_HOPS"), default=1)
    timeout = _parse_positive_float(os.getenv("SIMPLE_A2A_AUTONOMOUS_TIMEOUT"), default=20.0)
    return AutonomyConfig(
        agent_name=agent_name,
        self_url=self_url,
        discovery_urls=discovery_urls,
        max_hops=max_hops,
        timeout=timeout,
    )


def encode_autonomous_request(request: AutonomousRequest) -> str:
    payload = {
        "objective": request.objective,
        "origin_name": request.origin_name,
        "origin_url": request.origin_url,
        "remaining_hops": request.remaining_hops,
        "visited_urls": list(request.visited_urls),
        "relay_id": request.relay_id,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"{AUTONOMOUS_REQUEST_PREFIX}{encoded}"


def _normalize_url_sequence(values: Sequence[str]) -> tuple[str, ...]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_url(value)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        normalized_values.append(normalized)
    return tuple(normalized_values)


def decode_autonomous_request(text: str) -> AutonomousRequest | None:
    stripped = text.strip()
    if not stripped.startswith(AUTONOMOUS_REQUEST_PREFIX):
        return None

    payload_text = stripped.removeprefix(AUTONOMOUS_REQUEST_PREFIX)
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return None

    objective = str(payload.get("objective", "")).strip()
    origin_name = str(payload.get("origin_name", "")).strip()
    origin_url = str(payload.get("origin_url", "")).strip()
    relay_id = str(payload.get("relay_id", "")).strip()
    remaining_hops = _parse_non_negative_int(str(payload.get("remaining_hops", "0")), default=0)

    visited_payload = payload.get("visited_urls", [])
    visited_urls: tuple[str, ...]
    if isinstance(visited_payload, list):
        visited_urls = _normalize_url_sequence([str(item) for item in visited_payload])
    else:
        visited_urls = ()

    if not objective:
        objective = "relay message"
    if not origin_name:
        origin_name = "Unknown Agent"

    return AutonomousRequest(
        objective=objective,
        origin_name=origin_name,
        origin_url=origin_url,
        remaining_hops=remaining_hops,
        visited_urls=visited_urls,
        relay_id=relay_id,
    )


def _is_human_autonomy_trigger(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if normalized.startswith(AUTONOMOUS_REQUEST_PREFIX):
        return False

    japanese_target = ("他のagent" in normalized) or ("他のエージェント" in normalized)
    japanese_action = any(
        keyword in normalized for keyword in ("挨拶", "話しかけ", "会話", "検出", "見つけ", "探して")
    )
    if japanese_target and japanese_action:
        return True

    english_target = ("other agent" in lowered) or ("other agents" in lowered) or ("peer agent" in lowered)
    english_action = any(
        keyword in lowered for keyword in ("greet", "talk", "message", "say hi", "discover", "detect", "find")
    )
    return english_target and english_action


def _response_preview(text: str | None) -> list[str]:
    if not text:
        return ["(empty)"]

    clipped_text = text
    clipped = False
    if len(clipped_text) > MAX_RESPONSE_PREVIEW_CHARS:
        clipped_text = f"{clipped_text[:MAX_RESPONSE_PREVIEW_CHARS]}..."
        clipped = True

    lines = [line.rstrip() for line in clipped_text.splitlines()]
    if len(lines) > MAX_RESPONSE_PREVIEW_LINES:
        lines = lines[:MAX_RESPONSE_PREVIEW_LINES]
        clipped = True

    if clipped:
        lines.append("(truncated)")
    return lines or ["(empty)"]


def _ensure_relay_id(request: AutonomousRequest) -> AutonomousRequest:
    if request.relay_id:
        return request
    return AutonomousRequest(
        objective=request.objective,
        origin_name=request.origin_name,
        origin_url=request.origin_url,
        remaining_hops=request.remaining_hops,
        visited_urls=request.visited_urls,
        relay_id=f"relay-{uuid4().hex[:8]}",
    )


def _build_summary(
    *,
    config: AutonomyConfig,
    request: AutonomousRequest,
    discovered: Sequence[DiscoveredAgent],
    outcomes: Sequence[tuple[DiscoveredAgent, str | None, Exception | None]],
) -> str:
    lines = [
        "Autonomous outreach summary",
        f"relay_id: {request.relay_id}",
        f"agent: {config.agent_name}",
        f"self: {config.self_url or 'unknown'}",
        f"objective: {request.objective}",
        f"origin: {request.origin_name} ({request.origin_url or 'unknown'})",
        f"remaining_hops={request.remaining_hops}",
        f"detected agents: {len(discovered)}",
        f"reachable peers: {len(outcomes)}",
        f"contacted peers: {len(outcomes)}",
    ]

    if request.remaining_hops <= 0:
        lines.append("note: remaining_hops=0, no further outreach performed.")

    for agent in discovered:
        lines.append(f"- detected {agent.name} ({agent.url})")

    for peer, response, error in outcomes:
        if error is not None:
            lines.append(f"- contact {peer.name} ({peer.url}): ERROR {error}")
            continue
        lines.append(f"- contact {peer.name} ({peer.url}): OK")
        for response_line in _response_preview(response):
            lines.append(f"  | {response_line}")

    return "\n".join(lines)


def _build_conversation_message(objective: str, origin_name: str, self_name: str) -> str:
    lowered = objective.lower()
    is_greeting = any(k in lowered for k in ("挨拶", "greet", "話しかけ", "talk", "say hi", "hello", "こんにちは"))

    if is_greeting:
        return f"こんにちは！{origin_name}からの挨拶です。よろしくお願いします！"

    return f"{origin_name}からのメッセージ: {objective}"


async def maybe_handle_autonomous_request(
    user_text: str,
    *,
    config: AutonomyConfig | None = None,
    discover: DiscoverFn = discover_agents,
    send: SendFn = send_text_to_agent,
) -> tuple[str, bool] | None:
    resolved_config = config or load_autonomy_config_from_env()
    relay_request = decode_autonomous_request(user_text)

    if relay_request is None and not _is_human_autonomy_trigger(user_text):
        return None

    if relay_request is None:
        visited_urls = ()
        if resolved_config.self_url:
            visited_urls = (resolved_config.self_url,)

        relay_request = AutonomousRequest(
            objective=user_text.strip(),
            origin_name=resolved_config.agent_name,
            origin_url=resolved_config.self_url or "",
            remaining_hops=resolved_config.max_hops,
            visited_urls=visited_urls,
            relay_id=f"relay-{uuid4().hex[:8]}",
        )
    relay_request = _ensure_relay_id(relay_request)

    if not resolved_config.discovery_urls:
        return (
            "Autonomous outreach was requested, but SIMPLE_A2A_DISCOVERY_URLS is empty. "
            "Set comma-separated candidate agent URLs first.",
            True,
        )

    try:
        discovered = tuple(await discover(resolved_config.discovery_urls, timeout=resolved_config.timeout))
    except Exception as error:
        return f"Autonomous outreach failed during discovery: {error}", True

    normalized_self = _normalize_url(resolved_config.self_url)
    visited = set(relay_request.visited_urls)
    reachable_peers = [
        agent
        for agent in discovered
        if _normalize_url(agent.url) is not None
        and _normalize_url(agent.url) != normalized_self
        and _normalize_url(agent.url) not in visited
    ]

    outcomes: list[tuple[DiscoveredAgent, str | None, Exception | None]] = []
    logger.info(
        "[%s] autonomy start agent=%s self=%s remaining_hops=%s discovered=%s reachable=%s",
        relay_request.relay_id,
        resolved_config.agent_name,
        resolved_config.self_url,
        relay_request.remaining_hops,
        len(discovered),
        len(reachable_peers),
    )

    conversation_message = _build_conversation_message(
        relay_request.objective,
        relay_request.origin_name,
        resolved_config.agent_name,
    )

    if relay_request.remaining_hops > 0:
        next_visited = set(relay_request.visited_urls)
        if normalized_self:
            next_visited.add(normalized_self)
        next_request = AutonomousRequest(
            objective=relay_request.objective,
            origin_name=relay_request.origin_name,
            origin_url=relay_request.origin_url,
            remaining_hops=relay_request.remaining_hops - 1,
            visited_urls=tuple(sorted(next_visited)),
            relay_id=relay_request.relay_id,
        )
        encode_autonomous_request(next_request)

        for peer in reachable_peers:
            try:
                logger.info(
                    "[%s] contact start from=%s to=%s message=%s",
                    relay_request.relay_id,
                    resolved_config.self_url,
                    peer.url,
                    conversation_message[:50],
                )
                response = await send(peer.url, conversation_message, timeout=resolved_config.timeout)
            except Exception as error:
                logger.warning(
                    "[%s] contact failed from=%s to=%s error=%s",
                    relay_request.relay_id,
                    resolved_config.self_url,
                    peer.url,
                    error,
                )
                outcomes.append((peer, None, error))
                continue
            logger.info(
                "[%s] contact done from=%s to=%s response_chars=%s",
                relay_request.relay_id,
                resolved_config.self_url,
                peer.url,
                len(response),
            )
            outcomes.append((peer, response, None))

    summary = _build_summary(
        config=resolved_config,
        request=relay_request,
        discovered=discovered,
        outcomes=outcomes,
    )
    return summary, True
