import json
import time
from dataclasses import dataclass
from typing import Any

from backend.app.rag import retrieve_chunks
from backend.app.tools import SUPPORTED_ACTIONS


@dataclass
class AgentOutput:
    answer: str
    action: str
    action_input: str
    retrieved_chunks: list[str]
    latency_ms: int
    cost_usd: float


class AgentError(RuntimeError):
    pass


def estimate_claude_cost(input_tokens: int, output_tokens: int) -> float:
    input_per_million = 3.0
    output_per_million = 15.0
    return round((input_tokens / 1_000_000 * input_per_million) + (output_tokens / 1_000_000 * output_per_million), 6)


def _mock_answer(case: Any, facts: list[str]) -> tuple[str, str]:
    action_input = ", ".join(facts[:2]) if facts else case.expected_answer
    answer = f"{case.expected_answer} Key facts: {', '.join(facts)}."
    return answer, action_input


def run_mock_agent(case: Any, document_text: str, facts: list[str]) -> AgentOutput:
    started = time.perf_counter()
    chunks = retrieve_chunks(document_text, case.input)
    answer, action_input = _mock_answer(case, facts)
    return AgentOutput(
        answer=answer,
        action=case.expected_action,
        action_input=action_input,
        retrieved_chunks=chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=0.0,
    )


def _extract_text_from_claude_response(response: Any) -> str:
    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _parse_agent_json(raw: str) -> dict[str, str]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    parsed = json.loads(cleaned)
    action = str(parsed.get("action", "")).strip()
    if action not in SUPPORTED_ACTIONS:
        raise AgentError(f"Unsupported action returned: {action}")
    return {
        "answer": str(parsed.get("answer", "")).strip(),
        "action": action,
        "action_input": str(parsed.get("action_input", "")).strip(),
    }


def run_claude_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise AgentError("Anthropic SDK is not installed.") from exc
    if not api_key:
        raise AgentError("Claude mode requires Anthropic credentials in the local environment.")

    started = time.perf_counter()
    chunks = retrieve_chunks(document_text, case.input)
    prompt = {
        "document_context": chunks,
        "question": case.input,
        "allowed_actions": sorted(SUPPORTED_ACTIONS),
        "instructions": (
            "Answer only from the document context. Choose exactly one action. "
            "Return strict JSON with keys answer, action, action_input."
        ),
    }
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=450,
        temperature=0,
        messages=[{"role": "user", "content": json.dumps(prompt)}],
    )
    raw = _extract_text_from_claude_response(response)
    parsed = _parse_agent_json(raw)
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    return AgentOutput(
        answer=parsed["answer"],
        action=parsed["action"],
        action_input=parsed["action_input"],
        retrieved_chunks=chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=estimate_claude_cost(input_tokens, output_tokens),
    )
