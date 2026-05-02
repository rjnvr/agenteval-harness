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


def score_answer(answer: str, expected_answer: str, expected_facts: list[str]) -> float:
    answer_terms = tokenize(answer)
    expected_terms = tokenize(expected_answer)
    fact_hits = [1 for fact in expected_facts if tokenize(fact) <= answer_terms or fact.lower() in answer.lower()]
    fact_score = len(fact_hits) / max(len(expected_facts), 1)
    answer_score = len(answer_terms & expected_terms) / max(len(expected_terms), 1)
    return round((answer_score * 0.45) + (fact_score * 0.55), 3)


def hallucination_score(answer: str, document_text: str) -> float:
    if _contains_money_mismatch(answer, document_text):
        return 1.0
    answer_terms = {term for term in tokenize(answer) if len(term) > 5 and term not in GENERIC_ALLOWED}
    doc_terms = tokenize(document_text)
    unsupported = [term for term in answer_terms if term not in doc_terms]
    if not answer_terms:
        return 0.0
    return round(min(len(unsupported) / len(answer_terms), 1.0), 3)


def failure_type(
    answer_match: float,
    tool_correct: bool,
    hallucination: float,
    answer: str,
    expected_facts: list[str],
) -> str:
    if hallucination >= 0.45:
        return "hallucination"
    if not tool_correct:
        return "wrong_action"
    answer_terms = tokenize(answer)
    if any(not (tokenize(fact) <= answer_terms or fact.lower() in answer.lower()) for fact in expected_facts):
        return "missed_key_fact"
    if answer_match < 0.72:
        return "low_answer_match"
    return "none"


def failure_counts(results: list[object]) -> dict[str, int]:
    counter = Counter(result.failure_type for result in results if result.failure_type != "none")
    return dict(counter)
