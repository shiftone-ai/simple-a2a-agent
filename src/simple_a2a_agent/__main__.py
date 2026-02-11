"""Entry point for the A2A agent server/client CLI."""

import argparse
import asyncio
import os
from collections.abc import Sequence

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from simple_a2a_agent.a2a_client import send_text_to_agent
from simple_a2a_agent.agent import agent
from simple_a2a_agent.autonomy import load_autonomy_config_from_env
from simple_a2a_agent.executor import SimpleAgentExecutor
from simple_a2a_agent.model_config import load_model_from_env


def _resolve_public_url(host: str, port: int) -> str:
    configured_public_url = os.getenv("SIMPLE_A2A_PUBLIC_URL")
    if configured_public_url:
        return configured_public_url.strip()

    card_host = host
    if host in {"0.0.0.0", "::"}:
        card_host = "127.0.0.1"
    return f"http://{card_host}:{port}"


def build_agent_card(*, host: str, port: int) -> AgentCard:
    agent_name = os.getenv("SIMPLE_A2A_AGENT_NAME", "Simple Agent").strip() or "Simple Agent"
    agent_description = os.getenv(
        "SIMPLE_A2A_AGENT_DESCRIPTION", "A simple A2A-compatible agent powered by pydantic-ai"
    ).strip()
    return AgentCard(
        name=agent_name,
        description=agent_description,
        url=_resolve_public_url(host, port),
        version="0.1.0",
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="chat",
                name="Chat",
                description="General-purpose chat",
                tags=["chat"],
            )
        ],
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
    )


def create_app(*, host: str, port: int) -> A2AStarletteApplication:
    model = load_model_from_env()
    executor = SimpleAgentExecutor(
        agent=agent,
        model=model,
        autonomy_config=load_autonomy_config_from_env(host=host, port=port),
    )
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    return A2AStarletteApplication(agent_card=build_agent_card(host=host, port=port), http_handler=handler)


def run_server(host: str, port: int) -> None:
    uvicorn.run(create_app(host=host, port=port).build(), host=host, port=port)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simple A2A agent CLI")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Run the A2A server")
    serve_parser.add_argument("--host", default=os.getenv("A2A_HOST", "127.0.0.1"))
    serve_parser.add_argument("--port", type=int, default=int(os.getenv("A2A_PORT", "8000")))

    client_parser = subparsers.add_parser("client", help="Send a message to a remote A2A agent")
    client_parser.add_argument("--agent-url", default=os.getenv("SIMPLE_A2A_REMOTE_URL"))
    client_parser.add_argument("--message", required=True)
    client_parser.add_argument("--timeout", type=float, default=30.0)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        host = os.getenv("A2A_HOST", "127.0.0.1")
        port = int(os.getenv("A2A_PORT", "8000"))
        run_server(host=host, port=port)
        return 0

    if args.command == "serve":
        run_server(host=args.host, port=args.port)
        return 0

    if args.command == "client":
        if not args.agent_url:
            parser.error("--agent-url is required, or set SIMPLE_A2A_REMOTE_URL.")
        response = asyncio.run(
            send_text_to_agent(
                agent_url=args.agent_url,
                text=args.message,
                timeout=args.timeout,
            )
        )
        print(response)
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
