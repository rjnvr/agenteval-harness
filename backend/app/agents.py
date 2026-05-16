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


def estimate_gemini_cost(input_tokens: int, output_tokens: int) -> float:
    input_per_million = 0.30
    output_per_million = 2.50
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
    try:
        response = client.messages.create(
            model=model,
            max_tokens=450,
            temperature=0,
            messages=[{"role": "user", "content": json.dumps(_agent_prompt(case, chunks))}],
        )
    except Exception as exc:
        raise AgentError(f"Anthropic request failed: {exc}") from exc
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
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a strict document eval agent. Return only valid JSON."},
                {"role": "user", "content": json.dumps(_agent_prompt(case, chunks))},
            ],
        )
    except Exception as exc:
        raise AgentError(f"OpenAI request failed: {exc}") from exc
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


def run_google_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    try:
        from google import genai
    except ImportError as exc:
        raise AgentError("Google GenAI SDK is not installed.") from exc
    if not api_key:
        raise AgentError("Google Gemini provider requires an API key for this run. Keys are never stored.")

    started = time.perf_counter()
    chunks = retrieve_chunks(document_text, case.input)
    client = genai.Client(api_key=api_key)
    try:
        response = client.models.generate_content(
            model=model,
            contents=json.dumps(_agent_prompt(case, chunks)),
        )
    except Exception as exc:
        raise AgentError(f"Google Gemini request failed: {exc}") from exc
    raw = str(getattr(response, "text", "") or "")
    parsed = _parse_agent_json(raw)
    usage = getattr(response, "usage_metadata", None)
    input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    return AgentOutput(
        answer=parsed["answer"],
        action=parsed["action"],
        action_input=parsed["action_input"],
        retrieved_chunks=chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=estimate_gemini_cost(input_tokens, output_tokens),
    )


def run_openrouter_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AgentError("OpenAI SDK is not installed.") from exc
    if not api_key:
        raise AgentError("OpenRouter provider requires an API key for this run. Keys are never stored.")

    started = time.perf_counter()
    chunks = retrieve_chunks(document_text, case.input)
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a strict document eval agent. Return only valid JSON."},
                {"role": "user", "content": json.dumps(_agent_prompt(case, chunks))},
            ],
        )
    except Exception as exc:
        raise AgentError(f"OpenRouter request failed: {exc}") from exc
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
        cost_usd=0.0 if not (input_tokens or output_tokens) else estimate_openai_cost(model, input_tokens, output_tokens),
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
    elif provider == "google":
        try:
            from google import genai
        except ImportError as exc:
            raise AgentError("Google GenAI SDK is not installed.") from exc
        if not api_key:
            raise AgentError("LLM judge requires a Google Gemini API key.")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=json.dumps({
                "question": question,
                "expected_answer": expected_answer,
                "agent_answer": answer,
                "instructions": "Return strict JSON only: {\"score\": number between 0 and 1}.",
            }),
        )
        raw = str(getattr(response, "text", "") or "{}")
    elif provider == "openrouter":
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AgentError("OpenAI SDK is not installed.") from exc
        if not api_key:
            raise AgentError("LLM judge requires an OpenRouter API key.")
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
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


def summarize_eval_report(provider: str, model: str, api_key: str | None, report: dict[str, Any]) -> str:
    prompt = {
        "eval_report": report,
        "instructions": (
            "Write a concise but useful evaluation summary for a product/AI eval dashboard. "
            "Explain the overall result, that strict pass rate is an acceptance gate, how the score_breakdown "
            "quality signals differ from strict pass/fail, the most important failure modes, "
            "which cases are worth inspecting, likely root causes, and concrete next steps. "
            "Do not invent data not present in the report. Use plain text with short sections."
        ),
    }
    if provider == "mock":
        failure_counts = report.get("failure_counts", {})
        total_cases = int(report.get("total_cases", 0) or 0)
        pass_rate = float(report.get("pass_rate", 0) or 0)
        failures = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in dict(failure_counts).items()) or "none"
        breakdown = dict(report.get("score_breakdown", {}) or {})
        quality = ", ".join(f"{key.replace('_', ' ')}: {round(float(value) * 100)}%" for key, value in breakdown.items()) or "unavailable"
        return (
            f"Overall: latest run covered {total_cases} cases with a {round(pass_rate * 100)}% pass rate.\n\n"
            f"What it means: strict pass rate is the acceptance gate; the run {'passed cleanly' if pass_rate == 1 else 'has failures that need review'} under the current rubric.\n\n"
            f"Quality signals: {quality}.\n\n"
            f"Failure modes: {failures}.\n\n"
            "Next steps: inspect the failed cases, compare missed facts against expected facts, and rerun with Judge enabled when you want semantic scoring."
        )

    raw = "{}"
    if provider == "anthropic":
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise AgentError("Anthropic SDK is not installed.") from exc
        if not api_key:
            raise AgentError("Eval summary requires an Anthropic API key for this request.")
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=900,
            temperature=0,
            messages=[{"role": "user", "content": json.dumps(prompt)}],
        )
        return _extract_text_from_claude_response(response)
    if provider == "openai":
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AgentError("OpenAI SDK is not installed.") from exc
        if not api_key:
            raise AgentError("Eval summary requires an OpenAI API key for this request.")
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": "You summarize AI evaluation results for product teams."},
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )
        raw = response.choices[0].message.content or ""
    elif provider == "google":
        try:
            from google import genai
        except ImportError as exc:
            raise AgentError("Google GenAI SDK is not installed.") from exc
        if not api_key:
            raise AgentError("Eval summary requires a Google Gemini API key for this request.")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=json.dumps(prompt))
        raw = str(getattr(response, "text", "") or "")
    elif provider == "openrouter":
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AgentError("OpenAI SDK is not installed.") from exc
        if not api_key:
            raise AgentError("Eval summary requires an OpenRouter API key for this request.")
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": "You summarize AI evaluation results for product teams."},
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )
        raw = response.choices[0].message.content or ""
    else:
        raise AgentError(f"Unsupported summary provider: {provider}")

    return raw.strip() or "No summary was returned by the model."
