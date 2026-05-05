import re
from collections import Counter

from backend.app.rag import tokenize


MONEY_RE = re.compile(r"\$(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{2})?")
GENERIC_ALLOWED = {
    "action",
    "added",
    "agent",
    "answer",
    "approval",
    "approve",
    "because",
    "before",
    "claim",
    "compliance",
    "contract",
    "create",
    "documents",
    "expected",
    "facts",
    "follow",
    "information",
    "invoice",
    "missing",
    "payment",
    "request",
    "review",
    "should",
    "status",
    "total",
}


def _contains_money_mismatch(answer: str, document_text: str) -> bool:
    answer_amounts = set(MONEY_RE.findall(answer))
    doc_amounts = set(MONEY_RE.findall(document_text))
    return bool(answer_amounts - doc_amounts)


def fact_coverage(answer: str, expected_facts: list[str]) -> tuple[list[str], list[str]]:
    answer_terms = tokenize(answer)
    matched: list[str] = []
    missed: list[str] = []
    for fact in expected_facts:
        if tokenize(fact) <= answer_terms or fact.lower() in answer.lower():
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
    support_terms = tokenize(support_text)

    for amount in sorted(set(MONEY_RE.findall(answer)) - set(MONEY_RE.findall(support_text))):
        claims.append(amount)

    answer_terms = {term for term in tokenize(answer) if len(term) > 5 and term not in GENERIC_ALLOWED}
    for term in sorted(answer_terms):
        if term not in support_terms:
            claims.append(term)
    return claims[:12]


def hallucination_score(answer: str, document_text: str) -> float:
    if _contains_money_mismatch(answer, document_text):
        return 1.0
    answer_terms = {term for term in tokenize(answer) if len(term) > 5 and term not in GENERIC_ALLOWED}
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
        return "agent_error"
    if hallucination >= 0.45 or groundedness_value < 0.45:
        return "hallucination"
    if not tool_correct:
        return "wrong_action"
    answer_terms = tokenize(answer)
    if retrieval_hit_value < 0.5:
        return "missed_key_fact"
    if any(not (tokenize(fact) <= answer_terms or fact.lower() in answer.lower()) for fact in expected_facts):
        return "missed_key_fact"
    if action_input_score_value < 0.12:
        return "wrong_action"
    if answer_match < 0.72:
        return "low_answer_match"
    return "none"


def failure_counts(results: list[object]) -> dict[str, int]:
    counter = Counter(result.failure_type for result in results if result.failure_type != "none")
    return dict(counter)
