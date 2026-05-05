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
    schema_valid: bool = True


class AgentError(RuntimeError):
    pass


def estimate_claude_cost(input_tokens: int, output_tokens: int) -> float:
    input_per_million = 3.0
    output_per_million = 15.0
    return round((input_tokens / 1_000_000 * input_per_million) + (output_tokens / 1_000_000 * output_per_million), 6)


def estimate_openai_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    lowered = model.lower()
    if "mini" in lowered:
        input_per_million = 0.15
        output_per_million = 0.60
    else:
        input_per_million = 2.50
        output_per_million = 10.00
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


def _strip_code_fence(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    return cleaned


def _parse_agent_json(raw: str) -> dict[str, str]:
    parsed = json.loads(_strip_code_fence(raw))
    required = {"answer", "action", "action_input"}
    if not required <= set(parsed):
        missing = ", ".join(sorted(required - set(parsed)))
        raise AgentError(f"Model response missing required JSON fields: {missing}")
    action = str(parsed.get("action", "")).strip()
    if action not in SUPPORTED_ACTIONS:
        raise AgentError(f"Unsupported action returned: {action}")
    return {
        "answer": str(parsed.get("answer", "")).strip(),
        "action": action,
        "action_input": str(parsed.get("action_input", "")).strip(),
    }


def _agent_prompt(case: Any, chunks: list[str]) -> dict[str, Any]:
    return {
        "document_context": chunks,
        "question": case.input,
        "allowed_actions": sorted(SUPPORTED_ACTIONS),
        "instructions": (
            "Answer only from the document context. Choose exactly one action. "
            "Return strict JSON with keys answer, action, action_input. "
            "The action_input should contain the key reason, amount, task, or item for that action."
        ),
    }


def run_anthropic_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise AgentError("Anthropic SDK is not installed.") from exc
    if not api_key:
        raise AgentError("Anthropic provider requires an API key from the run request or ANTHROPIC_API_KEY.")

    started = time.perf_counter()
    chunks = retrieve_chunks(document_text, case.input)
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=450,
        temperature=0,
        messages=[{"role": "user", "content": json.dumps(_agent_prompt(case, chunks))}],
    )
    parsed = _parse_agent_json(_extract_text_from_claude_response(response))
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


def run_claude_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    return run_anthropic_agent(case, document_text, model, api_key)


def run_openai_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AgentError("OpenAI SDK is not installed.") from exc
    if not api_key:
        raise AgentError("OpenAI provider requires an API key from the run request or OPENAI_API_KEY.")

    started = time.perf_counter()
    chunks = retrieve_chunks(document_text, case.input)
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a strict document eval agent. Return only valid JSON."},
            {"role": "user", "content": json.dumps(_agent_prompt(case, chunks))},
        ],
    )
    raw = response.choices[0].message.content or ""
    parsed = _parse_agent_json(raw)
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return AgentOutput(
        answer=parsed["answer"],
        action=parsed["action"],
        action_input=parsed["action_input"],
        retrieved_chunks=chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=estimate_openai_cost(model, input_tokens, output_tokens),
    )


def judge_answer(provider: str, model: str, api_key: str | None, question: str, expected_answer: str, answer: str) -> float:
    if provider == "mock":
        return 1.0
    if provider == "anthropic":
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise AgentError("Anthropic SDK is not installed.") from exc
        if not api_key:
            raise AgentError("LLM judge requires an Anthropic API key.")
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=120,
            temperature=0,
            messages=[{"role": "user", "content": json.dumps({
                "question": question,
                "expected_answer": expected_answer,
                "agent_answer": answer,
                "instructions": "Return strict JSON only: {\"score\": number between 0 and 1}.",
            })}],
        )
        raw = _extract_text_from_claude_response(response)
    elif provider == "openai":
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AgentError("OpenAI SDK is not installed.") from exc
        if not api_key:
            raise AgentError("LLM judge requires an OpenAI API key.")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return only JSON with a numeric score field."},
                {"role": "user", "content": json.dumps({
                    "question": question,
                    "expected_answer": expected_answer,
                    "agent_answer": answer,
                    "instructions": "Score semantic correctness from 0 to 1.",
                })},
            ],
        )
        raw = response.choices[0].message.content or "{}"
    else:
        raise AgentError(f"Unsupported judge provider: {provider}")

    parsed = json.loads(_strip_code_fence(raw))
    score = float(parsed.get("score", 0))
    return round(max(min(score, 1.0), 0.0), 3)
