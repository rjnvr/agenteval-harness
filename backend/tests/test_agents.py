import pytest

from backend.app.agents import AgentError, _parse_agent_json


def test_openai_style_json_parses() -> None:
    parsed = _parse_agent_json('{"answer":"Booked","action":"book_meeting","action_input":"10 AM Pacific","proposed_slot":{"start":"2026-06-12T10:00:00-07:00","end":"2026-06-12T10:30:00-07:00"}}')

    assert parsed["action"] == "book_meeting"
    assert "2026-06-12T10:00:00-07:00" in parsed["proposed_slot"]


def test_anthropic_fenced_json_parses() -> None:
    parsed = _parse_agent_json('```json\n{"answer":"Need availability","action":"request_availability","action_input":"Jay availability","proposed_slot":""}\n```')

    assert parsed["action_input"] == "Jay availability"


def test_invalid_action_is_schema_error() -> None:
    with pytest.raises(AgentError):
        _parse_agent_json('{"answer":"Nope","action":"invent_tool","action_input":"x"}')
