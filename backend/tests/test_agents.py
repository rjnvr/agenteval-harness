import pytest

from backend.app.agents import AgentError, _parse_agent_json


def test_openai_style_json_parses() -> None:
    parsed = _parse_agent_json('{"answer":"Approved","action":"approve_invoice","action_input":"invoice INV-1"}')

    assert parsed["action"] == "approve_invoice"


def test_anthropic_fenced_json_parses() -> None:
    parsed = _parse_agent_json('```json\n{"answer":"Risk","action":"flag_risk","action_input":"missing docs"}\n```')

    assert parsed["action_input"] == "missing docs"


def test_invalid_action_is_schema_error() -> None:
    with pytest.raises(AgentError):
        _parse_agent_json('{"answer":"Nope","action":"invent_tool","action_input":"x"}')
