"""Tests for the simple A2A agent."""

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from simple_a2a_agent.agent import agent


class TestAgent:
    """Test pydantic-ai agent."""

    def test_agent_is_instance(self) -> None:
        assert isinstance(agent, Agent)

    def test_agent_responds(self) -> None:
        result = agent.run_sync("Hello", model=TestModel())
        assert isinstance(result.output, str)
        assert len(result.output) > 0
