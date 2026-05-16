import re
from collections import Counter

from backend.app.rag import tokenize

FAILURE_MODES = {
    "wrong_tool",
    "right_tool_wrong_args",
    "premature_stop",
    "ignored_constraint",
    "fabricated_tool_output",
    "unsupported_claim",
    "missed_key_fact",
    "retrieval_miss",
    "schema_invalid",
    "agent_error",
    "low_answer_quality",
    "none",
}

MONEY_RE = re.compile(r"\$(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{2})?")
HYPHEN_BETWEEN_ALNUM_RE = re.compile(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])")
GENERIC_ALLOWED = {
    "action",
    "added",
    "agent",
    "answer",
    "approval",
    "approve",
    "approved",
    "amount",
    "because",
    "before",
    "cannot",
    "claim",
    "compliance",
    "contract",
    "create",
    "documents",
    "exceeded",
    "expected",
    "facts",
    "follow",
    "information",
    "invoice",
    "missing",
    "payment",
    "proper",
    "request",
    "reporting",
    "required",
    "requirement",
    "review",
    "should",
    "status",
    "total",
    "validated",
    "verification",
    "without",
}


def normalize_for_support(text: str) -> str:
    return HYPHEN_BETWEEN_ALNUM_RE.sub(" ", text.lower())


def _contains_money_mismatch(answer: str, document_text: str) -> bool:
    answer_amounts = set(MONEY_RE.findall(answer))
    doc_amounts = set(MONEY_RE.findall(document_text))
    return bool(answer_amounts - doc_amounts)


def fact_coverage(answer: str, expected_facts: list[str]) -> tuple[list[str], list[str]]:
    normalized_answer = normalize_for_support(answer)
    answer_terms = tokenize(normalized_answer)
    matched: list[str] = []
    missed: list[str] = []
    for fact in expected_facts:
        normalized_fact = normalize_for_support(fact)
        if tokenize(normalized_fact) <= answer_terms or normalized_fact in normalized_answer:
            matched.append(fact)
        else:
            missed.append(fact)
    return matched, missed


def score_answer(answer: str, expected_answer: str, expected_facts: list[str]) -> float:
    answer_terms = tokenize(answer)
    expected_terms = tokenize(expected_answer)
    matched_facts, _ = fact_coverage(answer, expected_facts)
    fact_score = len(matched_facts) / max(len(expected_facts), 1)
    answer_score = len(answer_terms & expected_terms) / max(len(expected_terms), 1)
    return round((answer_score * 0.45) + (fact_score * 0.55), 3)


def fact_recall(answer: str, expected_facts: list[str]) -> float:
    matched, _ = fact_coverage(answer, expected_facts)
    return round(len(matched) / max(len(expected_facts), 1), 3)


def unsupported_claims(answer: str, support_text: str) -> list[str]:
    claims: list[str] = []
    normalized_answer = normalize_for_support(answer)
    normalized_support = normalize_for_support(support_text)
    support_terms = tokenize(normalized_support)

    for amount in sorted(set(MONEY_RE.findall(answer)) - set(MONEY_RE.findall(support_text))):
        claims.append(amount)

    answer_terms = {term for term in tokenize(normalized_answer) if len(term) > 7 and term not in GENERIC_ALLOWED}
    for term in sorted(answer_terms):
        if term not in support_terms:
            claims.append(term)
    return claims[:12]


def hallucination_score(answer: str, document_text: str) -> float:
    if _contains_money_mismatch(answer, document_text):
        return 1.0
    answer_terms = {term for term in tokenize(normalize_for_support(answer)) if len(term) > 7 and term not in GENERIC_ALLOWED}
    if not answer_terms:
        return 0.0
    unsupported = unsupported_claims(answer, document_text)
    return round(min(len(unsupported) / len(answer_terms), 1.0), 3)


def fact_precision(answer: str, document_text: str) -> float:
    return round(max(1.0 - hallucination_score(answer, document_text), 0.0), 3)


def retrieval_hit(retrieved_chunks: list[str], expected_facts: list[str]) -> float:
    retrieved_text = "\n".join(retrieved_chunks)
    matched, _ = fact_coverage(retrieved_text, expected_facts)
    return round(len(matched) / max(len(expected_facts), 1), 3)


def groundedness(answer: str, retrieved_chunks: list[str]) -> float:
    context = "\n".join(retrieved_chunks)
    if not context:
        return 0.0
    return round(max(1.0 - hallucination_score(answer, context), 0.0), 3)


def action_input_score(action_input: str, expected_answer: str, expected_facts: list[str]) -> float:
    expected_terms = tokenize(" ".join([expected_answer, *expected_facts]))
    input_terms = tokenize(action_input)
    if not expected_terms:
        return 1.0
    return round(len(input_terms & expected_terms) / len(expected_terms), 3)


def failure_type(
    answer_match: float,
    tool_correct: bool,
    hallucination: float,
    answer: str,
    expected_facts: list[str],
    *,
    schema_valid: bool = True,
    action_input_score_value: float = 1.0,
    retrieval_hit_value: float = 1.0,
    groundedness_value: float = 1.0,
) -> str:
    if not schema_valid:
        return "schema_invalid"
    if not answer.strip():
        return "premature_stop"
    if hallucination >= 0.45:
        return "fabricated_tool_output" if _contains_money_mismatch(answer, " ".join(expected_facts)) else "unsupported_claim"
    if groundedness_value < 0.45:
        return "unsupported_claim"
    if not tool_correct:
        return "wrong_tool"
    answer_terms = tokenize(answer)
    if retrieval_hit_value < 0.5:
        return "retrieval_miss"
    if any(not (tokenize(fact) <= answer_terms or fact.lower() in answer.lower()) for fact in expected_facts):
        return "missed_key_fact"
    if action_input_score_value < 0.12:
        return "right_tool_wrong_args"
    if answer_match < 0.72:
        return "low_answer_quality"
    return "none"


def failure_explanation(mode: str) -> str:
    explanations = {
        "wrong_tool": "Agent selected an action that does not match the expected tool.",
        "right_tool_wrong_args": "Agent selected the expected tool but supplied weak or missing action arguments.",
        "premature_stop": "Agent returned no usable answer before completing the task.",
        "ignored_constraint": "Agent answer ignored a task or document constraint.",
        "fabricated_tool_output": "Agent introduced a concrete value that is not supported by the document.",
        "unsupported_claim": "Agent answer includes claims not grounded in retrieved or source text.",
        "missed_key_fact": "Agent missed one or more expected facts from the document.",
        "retrieval_miss": "Retrieved context did not cover enough expected facts.",
        "schema_invalid": "Agent output did not satisfy the expected response schema.",
        "agent_error": "Agent call failed before a valid response could be scored.",
        "low_answer_quality": "Agent response had low semantic overlap with the expected answer.",
        "none": "No failure detected.",
    }
    return explanations.get(mode, "Failure did not match a known taxonomy mode.")


def failure_counts(results: list[object]) -> dict[str, int]:
    counter = Counter(
        getattr(result, "failure_mode", None) or result.failure_type
        for result in results
        if (getattr(result, "failure_mode", None) or result.failure_type) != "none"
    )
    return dict(counter)


def score_breakdown(result: object) -> dict[str, float]:
    tool_score = 1.0 if getattr(result, "tool_correct") else 0.0
    action_score = float(getattr(result, "action_input_score"))
    tool_accuracy = 1.0 if tool_score == 1.0 and action_score >= 0.12 else (tool_score * 0.7) + (action_score * 0.3)
    judge_score = getattr(result, "judge_score", None)
    semantic_quality = judge_score if judge_score is not None else getattr(result, "answer_match")
    return {
        "semantic_quality": round(float(semantic_quality), 3),
        "fact_completeness": round(float(getattr(result, "fact_recall")), 3),
        "tool_accuracy": round(tool_accuracy, 3),
        "grounding": round((float(getattr(result, "groundedness")) * 0.6) + (float(getattr(result, "fact_precision")) * 0.4), 3),
        "retrieval_quality": round(float(getattr(result, "retrieval_hit")), 3),
    }


def average_score_breakdown(results: list[object]) -> dict[str, float]:
    if not results:
        return {
            "semantic_quality": 0.0,
            "fact_completeness": 0.0,
            "tool_accuracy": 0.0,
            "grounding": 0.0,
            "retrieval_quality": 0.0,
        }
    breakdowns = [score_breakdown(result) for result in results]
    return {
        key: round(sum(item[key] for item in breakdowns) / len(breakdowns), 3)
        for key in breakdowns[0]
    }
