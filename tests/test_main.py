"""Tests for CLI entrypoint."""

import pytest

from simple_a2a_agent.__main__ import main


def test_main_defaults_to_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, int | str] = {}

    def fake_run_server(host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port

    monkeypatch.setenv("A2A_HOST", "0.0.0.0")
    monkeypatch.setenv("A2A_PORT", "9000")
    monkeypatch.setattr("simple_a2a_agent.__main__.run_server", fake_run_server)

    exit_code = main([])

    assert exit_code == 0
    assert called == {"host": "0.0.0.0", "port": 9000}


def test_main_client_mode_prints_response(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_send_text_to_agent(agent_url: str, text: str, timeout: float = 30.0) -> str:
        assert agent_url == "http://agent.example"
        assert text == "hello"
        assert timeout == 12.5
        return "remote says hi"

    monkeypatch.setattr("simple_a2a_agent.__main__.send_text_to_agent", fake_send_text_to_agent)

    exit_code = main(
        [
            "client",
            "--agent-url",
            "http://agent.example",
            "--message",
            "hello",
            "--timeout",
            "12.5",
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "remote says hi"


def test_main_client_mode_uses_env_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def fake_send_text_to_agent(agent_url: str, text: str, timeout: float = 30.0) -> str:
        assert agent_url == "http://env-agent.example"
        assert text == "hello"
        assert timeout == 30.0
        return "ok"

    monkeypatch.setenv("SIMPLE_A2A_REMOTE_URL", "http://env-agent.example")
    monkeypatch.setattr("simple_a2a_agent.__main__.send_text_to_agent", fake_send_text_to_agent)

    exit_code = main(["client", "--message", "hello"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "ok"


def test_main_client_mode_requires_agent_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMPLE_A2A_REMOTE_URL", raising=False)

    with pytest.raises(SystemExit, match="2"):
        main(["client", "--message", "hello"])
