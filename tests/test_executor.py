"""Tests for the A2A agent executor."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import Message, Part, Role, TaskState, TextPart
from a2a.utils.message import get_message_text
from pydantic_ai.models.test import TestModel

from simple_a2a_agent.agent import agent
from simple_a2a_agent.executor import MAX_USER_INPUT_LENGTH, SimpleAgentExecutor


@pytest.fixture
def executor() -> SimpleAgentExecutor:
    return SimpleAgentExecutor(agent=agent, model=TestModel())


def _build_context(message_text: str | None) -> MagicMock:
    context = MagicMock(spec=RequestContext)
    context.message = (
        None
        if message_text is None
        else Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=message_text))],
            message_id="msg-1",
        )
    )
    context.task_id = "task-1"
    context.context_id = "ctx-1"
    return context


def _build_mocked_executor(
    *,
    run_side_effect: Exception | None = None,
    run_output: str = "ok",
) -> tuple[SimpleAgentExecutor, AsyncMock]:
    run_mock = AsyncMock()
    if run_side_effect is None:
        run_mock.return_value = MagicMock(output=run_output)
    else:
        run_mock.side_effect = run_side_effect

    agent_mock = MagicMock()
    agent_mock.run = run_mock
    return SimpleAgentExecutor(agent=agent_mock), run_mock


class TestSimpleAgentExecutor:
    """Test A2A executor wrapping pydantic-ai agent."""

    @pytest.mark.anyio
    async def test_execute_returns_completed_task(self, executor: SimpleAgentExecutor) -> None:
        context = _build_context("Hello")
        event_queue = AsyncMock(spec=EventQueue)

        await executor.execute(context, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        event = event_queue.enqueue_event.await_args.args[0]

        assert event.status.state == TaskState.completed
        assert event.status.message is not None

    @pytest.mark.anyio
    async def test_execute_prefers_autonomous_handler_when_triggered(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        executor, run_mock = _build_mocked_executor(run_output="llm output")
        context = _build_context("他のagentに挨拶してみてください")
        event_queue = AsyncMock(spec=EventQueue)

        async def fake_autonomous_handler(user_text: str, *_args, **_kwargs) -> tuple[str, bool] | None:
            assert user_text == "他のagentに挨拶してみてください"
            return ("autonomous output", True)

        monkeypatch.setattr(
            "simple_a2a_agent.executor.maybe_handle_autonomous_request",
            fake_autonomous_handler,
        )

        await executor.execute(context, event_queue)

        run_mock.assert_not_awaited()
        event_queue.enqueue_event.assert_awaited_once()
        event = event_queue.enqueue_event.await_args.args[0]
        assert event.status.state == TaskState.completed
        assert event.status.message is not None
        assert get_message_text(event.status.message) == "autonomous output"

    @pytest.mark.anyio
    async def test_execute_returns_failed_task_when_agent_raises(self) -> None:
        executor, _ = _build_mocked_executor(run_side_effect=RuntimeError("upstream timeout"))
        context = _build_context("Hello")
        event_queue = AsyncMock(spec=EventQueue)

        await executor.execute(context, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        event = event_queue.enqueue_event.await_args.args[0]

        assert event.status.state == TaskState.failed
        assert event.status.message is not None
        assert get_message_text(event.status.message) == "Agent execution failed. Please try again later."

    @pytest.mark.anyio
    async def test_execute_returns_failed_task_for_empty_message(self) -> None:
        executor, run_mock = _build_mocked_executor()
        context = _build_context(None)
        event_queue = AsyncMock(spec=EventQueue)

        await executor.execute(context, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        run_mock.assert_not_awaited()
        event = event_queue.enqueue_event.await_args.args[0]

        assert event.status.state == TaskState.failed
        assert event.status.message is not None
        assert get_message_text(event.status.message) == "Input message must not be empty."

    @pytest.mark.anyio
    async def test_execute_returns_failed_task_for_too_long_message(self) -> None:
        executor, run_mock = _build_mocked_executor()
        context = _build_context("x" * (MAX_USER_INPUT_LENGTH + 1))
        event_queue = AsyncMock(spec=EventQueue)

        await executor.execute(context, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        run_mock.assert_not_awaited()
        event = event_queue.enqueue_event.await_args.args[0]

        assert event.status.state == TaskState.failed
        assert event.status.message is not None
        assert (
            get_message_text(event.status.message)
            == f"Input message is too long. Maximum length is {MAX_USER_INPUT_LENGTH} characters."
        )

    @pytest.mark.anyio
    async def test_cancel_returns_canceled_task(self, executor: SimpleAgentExecutor) -> None:
        context = _build_context("ignored")
        event_queue = AsyncMock(spec=EventQueue)

        await executor.cancel(context, event_queue)

        event_queue.enqueue_event.assert_awaited_once()
        event = event_queue.enqueue_event.await_args.args[0]
        assert event.status.state == TaskState.canceled
