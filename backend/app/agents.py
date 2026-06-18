import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.app.dataset import context_lines, expected_decision
from backend.app.domains.documentation import DOC_ACTIONS
from backend.app.tools import SUPPORTED_ACTIONS

WEBHOOK_TIMEOUT_SECONDS = 30.0
WEBHOOK_MAX_RESPONSE_BYTES = 1_000_000


@dataclass
class AgentOutput:
    answer: str
    action: str
    action_input: str
    retrieved_chunks: list[str]
    latency_ms: int
    cost_usd: float
    schema_valid: bool = True
    proposed_slot: str = ""
    citations: list[str] = field(default_factory=list)


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


def _slot_text(slot: Any) -> str:
    if isinstance(slot, dict):
        return json.dumps({"start": slot.get("start", ""), "end": slot.get("end", "")}, sort_keys=True)
    return str(slot or "")


def run_mock_agent(case: Any, document_text: str, facts: list[str]) -> AgentOutput:
    started = time.perf_counter()
    chunks = context_lines(case)
    decision = expected_decision(case)
    answer, action_input = _mock_answer(case, facts)
    proposed_slot = _slot_text(decision.get("slot"))
    if proposed_slot:
        action_input = f"{action_input}; slot {proposed_slot}"
    return AgentOutput(
        answer=answer,
        action=case.expected_action,
        action_input=action_input,
        retrieved_chunks=chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=0.0,
        proposed_slot=proposed_slot,
    )


def run_naive_agent(case: Any, document_text: str, facts: list[str]) -> AgentOutput:
    started = time.perf_counter()
    chunks = context_lines(case)
    naive_slots = {
        "case_001": {"start": "2026-06-10T07:00:00-07:00", "end": "2026-06-10T07:30:00-07:00"},
        "case_003": {"start": "2026-06-11T09:00:00+01:00", "end": "2026-06-11T09:30:00+01:00"},
        "case_004": {"start": "2026-06-12T10:00:00-07:00", "end": "2026-06-12T10:30:00-07:00"},
        "case_005": {"start": "2026-06-15T09:00:00-07:00", "end": "2026-06-15T09:30:00-07:00"},
        "case_007": {"start": "2026-06-19T10:00:00-07:00", "end": "2026-06-19T10:30:00-07:00"},
        "case_009": {"start": "2026-06-16T19:00:00-07:00", "end": "2026-06-16T19:30:00-07:00"},
        "case_010": {"start": "2026-06-17T11:00:00-06:00", "end": "2026-06-17T11:30:00-06:00"},
        "case_012": {"start": "2026-06-18T12:00:00-07:00", "end": "2026-06-18T12:30:00-07:00"},
        "case_014": {"start": "2026-06-24T09:00:00-07:00", "end": "2026-06-24T09:30:00-07:00"},
        "case_015": {"start": "2026-06-25T11:00:00-07:00", "end": "2026-06-25T11:30:00-07:00"},
    }
    decision = expected_decision(case)
    slot = naive_slots.get(case.id, decision.get("slot") if isinstance(decision, dict) else None)
    proposed_slot = _slot_text(slot)
    action = "book_meeting" if proposed_slot else case.expected_action
    if case.expected_action == "propose_alternative":
        action = "propose_alternative"
    answer = f"I will use the first obvious calendar opening. Key facts: {', '.join(facts[:1])}."
    return AgentOutput(
        answer=answer,
        action=action,
        action_input=f"first visible opening {proposed_slot}".strip(),
        retrieved_chunks=chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=0.0,
        proposed_slot=proposed_slot,
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
        "proposed_slot": _slot_text(parsed.get("proposed_slot", "")),
    }


def _agent_prompt(case: Any, chunks: list[str]) -> dict[str, Any]:
    return {
        "document_context": chunks,
        "question": case.input,
        "allowed_actions": sorted(SUPPORTED_ACTIONS),
        "instructions": (
            "You are evaluating a coordination and scheduling request. Use only the assembled "
            "calendar, timezone, participant, and preference context. Choose exactly one action. "
            "Return strict JSON with keys answer, action, action_input, proposed_slot, reasoning. "
            "proposed_slot should be {start,end} ISO datetimes with timezone offsets when the action proposes or books a time; otherwise use an empty string."
        ),
    }


def _parse_doc_agent_json(raw: str) -> dict[str, Any]:
    parsed = json.loads(_strip_code_fence(raw))
    if not {"answer", "action"} <= set(parsed):
        missing = ", ".join(sorted({"answer", "action"} - set(parsed)))
        raise AgentError(f"Model response missing required JSON fields: {missing}")
    action = str(parsed.get("action", "")).strip()
    if action not in DOC_ACTIONS:
        raise AgentError(f"Unsupported action returned: {action}")
    citations_raw = parsed.get("citations", [])
    citations = [str(item).strip() for item in citations_raw if str(item).strip()] if isinstance(citations_raw, list) else []
    return {
        "answer": str(parsed.get("answer", "")).strip(),
        "action": action,
        "action_input": str(parsed.get("action_input", "")).strip(),
        "proposed_slot": "",
        "citations": citations,
    }


def _doc_agent_prompt(case: Any, chunks: list[str]) -> dict[str, Any]:
    return {
        "retrieved_chunks": chunks,
        "question": case.input,
        "allowed_actions": sorted(DOC_ACTIONS),
        "instructions": (
            "You are a documentation assistant. Answer the question using ONLY the retrieved "
            "documentation chunks. Cite the source page id(s) you used in a 'citations' array. "
            "If the answer is not present in the chunks, respond with action 'insufficient_context' "
            "instead of guessing. Return strict JSON with keys answer, action, action_input, citations."
        ),
    }


def run_mock_doc_agent(
    case: Any,
    retrieved_chunks: list[str],
    facts: list[str],
    expected_sources: list[str],
) -> AgentOutput:
    """Competent baseline: answers grounded in the facts, cites the right page, refuses honestly."""
    started = time.perf_counter()
    if case.expected_action == "insufficient_context":
        answer = "That topic is not covered in the current documentation, so I cannot answer from the docs."
        return AgentOutput(
            answer=answer,
            action="insufficient_context",
            action_input="not documented",
            retrieved_chunks=retrieved_chunks,
            latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
            cost_usd=0.0,
            citations=[],
        )
    answer = f"{case.expected_answer} {' '.join(facts)}".strip()
    return AgentOutput(
        answer=answer,
        action=case.expected_action,
        action_input=", ".join(facts[:2]) if facts else case.expected_answer,
        retrieved_chunks=retrieved_chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=0.0,
        citations=list(expected_sources),
    )


def run_naive_doc_agent(case: Any, retrieved_chunks: list[str], facts: list[str]) -> AgentOutput:
    """Intentionally bad: answers everything confidently, never refuses, never cites, and invents detail."""
    started = time.perf_counter()
    answer = (
        f"Yes, that is fully supported. {case.input} works out of the box via the "
        "undocumentedoverride configuration flag."
    )
    return AgentOutput(
        answer=answer,
        action="answer",
        action_input="confident guess",
        retrieved_chunks=retrieved_chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=0.0,
        citations=[],
    )


def run_anthropic_agent(
    case: Any,
    document_text: str,
    model: str,
    api_key: str | None,
    *,
    chunks: list[str] | None = None,
    prompt_builder: Callable[[Any, list[str]], dict[str, Any]] | None = None,
    parser: Callable[[str], dict[str, Any]] | None = None,
) -> AgentOutput:
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise AgentError("Anthropic SDK is not installed.") from exc
    if not api_key:
        raise AgentError("Anthropic provider requires an API key from the run request or ANTHROPIC_API_KEY.")

    started = time.perf_counter()
    chunks = context_lines(case) if chunks is None else chunks
    build_prompt = prompt_builder or _agent_prompt
    parse = parser or _parse_agent_json
    client = Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=450,
            temperature=0,
            messages=[{"role": "user", "content": json.dumps(build_prompt(case, chunks))}],
        )
    except Exception as exc:
        raise AgentError(f"Anthropic request failed: {exc}") from exc
    parsed = parse(_extract_text_from_claude_response(response))
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
        proposed_slot=parsed["proposed_slot"],
        citations=parsed.get("citations", []),
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
    chunks = context_lines(case)
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
        proposed_slot=parsed["proposed_slot"],
    )


def run_google_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    try:
        from google import genai
    except ImportError as exc:
        raise AgentError("Google GenAI SDK is not installed.") from exc
    if not api_key:
        raise AgentError("Google Gemini provider requires an API key for this run. Keys are never stored.")

    started = time.perf_counter()
    chunks = context_lines(case)
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
        proposed_slot=parsed["proposed_slot"],
    )


def run_openrouter_agent(case: Any, document_text: str, model: str, api_key: str | None) -> AgentOutput:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AgentError("OpenAI SDK is not installed.") from exc
    if not api_key:
        raise AgentError("OpenRouter provider requires an API key for this run. Keys are never stored.")

    started = time.perf_counter()
    chunks = context_lines(case)
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
        proposed_slot=parsed["proposed_slot"],
    )


def run_webhook_agent(
    case: Any,
    document_text: str,
    webhook_url: str,
    webhook_headers: dict[str, str] | None,
) -> AgentOutput:
    if not webhook_url or not webhook_url.strip():
        raise AgentError("Webhook provider requires a webhook_url.")
    parsed_url = webhook_url.strip()
    if not (parsed_url.startswith("http://") or parsed_url.startswith("https://")):
        raise AgentError("webhook_url must start with http:// or https://.")

    started = time.perf_counter()
    chunks = context_lines(case)
    payload = {
        "case_id": case.id,
        "question": case.input,
        "allowed_actions": sorted(SUPPORTED_ACTIONS),
        "document": {
            "id": case.document.id,
            "name": case.document.name,
            "category": case.document.category,
            "text": document_text,
        },
        "context": getattr(case, "context_json", "{}"),
        "expected_decision": getattr(case, "expected_decision_json", "{}"),
        "retrieved_chunks": chunks,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "AgentEval-Harness/1.0"}
    for key, value in (webhook_headers or {}).items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.strip():
            headers[key.strip()] = value
    request = urllib.request.Request(parsed_url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:
            raw_bytes = response.read(WEBHOOK_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise AgentError(f"Webhook returned HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise AgentError(f"Webhook request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AgentError(f"Webhook request timed out after {WEBHOOK_TIMEOUT_SECONDS:.0f}s.") from exc
    if len(raw_bytes) > WEBHOOK_MAX_RESPONSE_BYTES:
        raise AgentError("Webhook response exceeded 1MB size limit.")
    try:
        decoded = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AgentError("Webhook response was not valid UTF-8.") from exc
    parsed = _parse_agent_json(decoded)
    try:
        body_json = json.loads(_strip_code_fence(decoded))
    except json.JSONDecodeError as exc:
        raise AgentError(f"Webhook response was not valid JSON: {exc}") from exc

    returned_chunks_raw = body_json.get("retrieved_chunks")
    if isinstance(returned_chunks_raw, list):
        returned_chunks = [str(item) for item in returned_chunks_raw if isinstance(item, (str, int, float))]
    else:
        returned_chunks = chunks

    cost_raw = body_json.get("cost_usd", 0)
    try:
        cost_usd = float(cost_raw)
    except (TypeError, ValueError):
        cost_usd = 0.0
    cost_usd = max(cost_usd, 0.0)

    return AgentOutput(
        answer=parsed["answer"],
        action=parsed["action"],
        action_input=parsed["action_input"],
        retrieved_chunks=returned_chunks,
        latency_ms=max(int((time.perf_counter() - started) * 1000), 1),
        cost_usd=round(cost_usd, 6),
        proposed_slot=parsed["proposed_slot"],
    )


def judge_answer(provider: str, model: str, api_key: str | None, question: str, expected_answer: str, answer: str) -> float:
    if provider in {"mock", "naive"}:
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
