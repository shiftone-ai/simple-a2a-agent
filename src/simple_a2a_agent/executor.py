"""A2A AgentExecutor wrapping a pydantic-ai Agent."""

import logging
from uuid import uuid4

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Task, TaskState, TaskStatus
from a2a.utils.message import get_message_text, new_agent_text_message
from pydantic_ai import Agent
from pydantic_ai.models import KnownModelName, Model

from simple_a2a_agent.autonomy import AutonomyConfig, maybe_handle_autonomous_request

MAX_USER_INPUT_LENGTH = 8_000
logger = logging.getLogger(__name__)


def _resolved_ids(context: RequestContext) -> tuple[str, str]:
    task_id = context.task_id or f"task-{uuid4()}"
    context_id = context.context_id or f"ctx-{uuid4()}"
    return task_id, context_id


class SimpleAgentExecutor(AgentExecutor):
    """Bridges pydantic-ai Agent to A2A protocol."""

    def __init__(
        self,
        agent: Agent[None, str],
        model: Model | KnownModelName | None = None,
        autonomy_config: AutonomyConfig | None = None,
    ) -> None:
        self._agent = agent
        self._model = model
        self._autonomy_config = autonomy_config

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id, context_id = _resolved_ids(context)
        user_text = get_message_text(context.message) if context.message else ""
        if not user_text.strip():
            await event_queue.enqueue_event(
                Task(
                    id=task_id,
                    context_id=context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            "Input message must not be empty.",
                            context_id,
                            task_id,
                        ),
                    ),
                )
            )
            return

        if len(user_text) > MAX_USER_INPUT_LENGTH:
            await event_queue.enqueue_event(
                Task(
                    id=task_id,
                    context_id=context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            f"Input message is too long. Maximum length is {MAX_USER_INPUT_LENGTH} characters.",
                            context_id,
                            task_id,
                        ),
                    ),
                )
            )
            return

        output_text: str
        try:
            autonomy_result = await maybe_handle_autonomous_request(
                user_text,
                config=self._autonomy_config,
            )
            if autonomy_result is not None:
                autonomous_output, _is_autonomous = autonomy_result
                output_text = autonomous_output
            else:
                result = await self._agent.run(user_text, model=self._model)
                output_text = result.output
        except Exception:
            logger.exception("Agent execution failed for task_id=%s", task_id)
            await event_queue.enqueue_event(
                Task(
                    id=task_id,
                    context_id=context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(
                            "Agent execution failed. Please try again later.",
                            context_id,
                            task_id,
                        ),
                    ),
                )
            )
            return

        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.completed,
                    message=new_agent_text_message(
                        output_text,
                        context_id,
                        task_id,
                    ),
                ),
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id, context_id = _resolved_ids(context)
        await event_queue.enqueue_event(
            Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(state=TaskState.canceled),
            )
        )
