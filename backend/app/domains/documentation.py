"""Documentation Q&A eval domain.

Evaluates a docs assistant (the "ask AI" use case): given a user question and
chunks retrieved from a documentation corpus, the agent must answer grounded in
those chunks, cite the right source, and honestly refuse when the answer is not
in the docs. This module reuses the generic RAG metrics in ``evaluator`` and adds
the doc-specific scorers (context precision, citation accuracy, refusal calibration)
plus a documentation failure taxonomy and score breakdown.
"""
from __future__ import annotations

from typing import Any

from backend.app import evaluator
from backend.app.rag import chunk_text, tokenize

# The decision surface for a documentation Q&A agent.
DOC_ACTIONS = {
    "answer",                 # answer the question from the docs
    "answer_with_citation",   # answer and cite the source page(s)
    "insufficient_context",   # the answer is not in the docs; say so instead of guessing
    "escalate_to_human",      # out of scope / ambiguous; hand back to a person
}

# Actions where the agent is making a factual claim that must be grounded + cited.
ANSWER_ACTIONS = {"answer", "answer_with_citation"}
# Actions that decline to answer from the docs.
REFUSAL_ACTIONS = {"insufficient_context", "escalate_to_human"}

DOC_FAILURE_MODES = {
    "hallucinated_answer",
    "missing_citation",
    "wrong_citation",
    "incomplete_answer",
    "retrieval_miss",
    "should_have_refused",
    "over_refusal",
    "schema_invalid",
    "agent_error",
    "low_answer_quality",
    "none",
}

# Pass thresholds for the documentation domain.
ANSWER_RELEVANCY_MIN = 0.6
FAITHFULNESS_MIN = 0.6
CONTEXT_RECALL_MIN = 0.5
HALLUCINATION_MAX = 0.3
CITATION_MIN = 0.5


def retrieve_corpus_chunks(documents: list[Any], question: str, top_k: int = 3) -> list[tuple[str, str]]:
    """Rank chunks across the whole documentation corpus for a question.

    Returns ``(source_doc_id, chunk_text)`` pairs, best first. Retrieval can fail by
    surfacing chunks from the wrong page, which is exactly what context recall/precision
    are meant to catch.
    """
    query_terms = tokenize(question)
    scored: list[tuple[int, int, str, str]] = []
    for document in documents:
        doc_id = str(getattr(document, "id", ""))
        for chunk in chunk_text(str(getattr(document, "text", ""))):
            chunk_terms = tokenize(chunk)
            overlap = len(query_terms & chunk_terms)
            scored.append((overlap, len(chunk_terms), doc_id, chunk))
    # Prefer higher query overlap, then shorter (more focused) chunks.
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [(doc_id, chunk) for _overlap, _size, doc_id, chunk in scored[:top_k]]


def context_precision(retrieved_chunks: list[str], required_facts: list[str]) -> float:
    """Fraction of retrieved chunks that carry at least one required fact.

    Complements ``evaluator.retrieval_hit`` (context recall): recall asks whether the
    needed facts were retrieved at all; precision asks whether retrieval wasted slots on
    irrelevant chunks.
    """
    if not retrieved_chunks:
        return 0.0
    if not required_facts:
        return 1.0
    relevant = 0
    for chunk in retrieved_chunks:
        matched, _ = evaluator.fact_coverage(chunk, required_facts)
        if matched:
            relevant += 1
    return round(relevant / len(retrieved_chunks), 3)


def _normalize_source(value: str) -> str:
    return value.strip().lower().removesuffix(".txt").removesuffix(".md").removesuffix(".mdx")


def citation_score(citations: list[str], expected_sources: list[str]) -> float:
    """Recall of the expected source pages among the agent's citations.

    Full credit when no citation is expected (e.g. a correct refusal). Matching is
    lenient: an expected source counts as cited if its id appears in any citation string.
    """
    expected = [_normalize_source(src) for src in expected_sources if str(src).strip()]
    if not expected:
        return 1.0
    cited = [_normalize_source(c) for c in citations if str(c).strip()]
    if not cited:
        return 0.0
    matched = sum(1 for src in expected if any(src in c or c in src for c in cited))
    return round(matched / len(expected), 3)


def refusal_correct(action: str, expected_action: str) -> bool:
    """Whether the agent's decision to answer vs. refuse matched the case.

    For unanswerable cases (``expected_action == "insufficient_context"``) the agent
    must refuse; for answerable cases it must not wrongly refuse.
    """
    refused = action in REFUSAL_ACTIONS
    if expected_action == "insufficient_context":
        return refused
    return not refused


def documentation_failure_type(
    *,
    schema_valid: bool,
    agent_failed: bool,
    expected_action: str,
    action: str,
    answer_relevancy: float,
    faithfulness: float,
    hallucination: float,
    context_recall: float,
    citation: float,
    citation_expected: bool,
    citations: list[str],
    missed_facts: list[str],
) -> str:
    if not schema_valid:
        return "schema_invalid"
    if agent_failed:
        return "agent_error"
    refused = action in REFUSAL_ACTIONS
    unanswerable = expected_action == "insufficient_context"
    if unanswerable and not refused:
        return "should_have_refused"
    if not unanswerable and refused:
        return "over_refusal"
    if unanswerable and refused:
        return "none"
    # From here the case is answerable and the agent answered.
    if hallucination >= HALLUCINATION_MAX or faithfulness < FAITHFULNESS_MIN:
        return "hallucinated_answer"
    if context_recall < CONTEXT_RECALL_MIN:
        return "retrieval_miss"
    if citation_expected and not citations:
        return "missing_citation"
    if citation_expected and citation < CITATION_MIN:
        return "wrong_citation"
    if missed_facts:
        return "incomplete_answer"
    if answer_relevancy < ANSWER_RELEVANCY_MIN:
        return "low_answer_quality"
    return "none"


DOC_FAILURE_EXPLANATIONS = {
    "hallucinated_answer": "Agent stated something not grounded in the retrieved documentation.",
    "missing_citation": "Agent answered without citing the source page it should have.",
    "wrong_citation": "Agent cited the wrong documentation page(s) for its answer.",
    "incomplete_answer": "Agent missed one or more facts the answer was expected to cover.",
    "retrieval_miss": "The needed documentation was not retrieved for this question.",
    "should_have_refused": "Answer is not in the docs; the agent should have said so instead of guessing.",
    "over_refusal": "The answer was in the docs, but the agent refused to answer.",
    "schema_invalid": "Agent output did not satisfy the expected response schema.",
    "agent_error": "Agent call failed before a valid response could be scored.",
    "low_answer_quality": "Agent response had low semantic overlap with the expected answer.",
    "none": "No failure detected.",
}


def documentation_failure_explanation(mode: str) -> str:
    return DOC_FAILURE_EXPLANATIONS.get(mode, "Failure did not match a known documentation taxonomy mode.")


def evaluate_documentation_output(
    *,
    output: Any,
    required_facts: list[str],
    expected_answer: str,
    expected_action: str,
    acceptable_actions: list[str],
    expected_sources: list[str],
    corpus_text: str,
    agent_failed: bool,
) -> dict[str, Any]:
    """Compute the full documentation metric bundle + failure mode for one case."""
    answer = output.answer
    chunks = output.retrieved_chunks
    citations = list(getattr(output, "citations", []) or [])

    answer_relevancy = evaluator.score_answer(answer, expected_answer, required_facts)
    matched_facts, missed_facts = evaluator.fact_coverage(answer, required_facts)
    context_recall = evaluator.retrieval_hit(chunks, required_facts)
    precision = context_precision(chunks, required_facts)
    faithfulness = evaluator.groundedness(answer, chunks)
    hallucination = evaluator.hallucination_score(answer, corpus_text)
    unsupported = evaluator.unsupported_claims(answer, corpus_text)

    unanswerable = expected_action == "insufficient_context"
    refused = output.action in REFUSAL_ACTIONS
    refusal_ok = refusal_correct(output.action, expected_action)
    citation_expected = (not unanswerable) and bool(expected_sources)
    citation = 1.0 if (unanswerable and refused) else citation_score(citations, expected_sources)
    tool_correct = output.action in acceptable_actions

    fail_mode = "agent_error" if agent_failed else documentation_failure_type(
        schema_valid=output.schema_valid,
        agent_failed=agent_failed,
        expected_action=expected_action,
        action=output.action,
        answer_relevancy=answer_relevancy,
        faithfulness=faithfulness,
        hallucination=hallucination,
        context_recall=context_recall,
        citation=citation,
        citation_expected=citation_expected,
        citations=citations,
        missed_facts=missed_facts,
    )

    passed = (
        fail_mode == "none"
        and output.schema_valid
        and refusal_ok
        and (
            # Correct refusal on an unanswerable question is a full pass.
            (unanswerable and refused)
            or (
                answer_relevancy >= ANSWER_RELEVANCY_MIN
                and faithfulness >= FAITHFULNESS_MIN
                and context_recall >= CONTEXT_RECALL_MIN
                and hallucination < HALLUCINATION_MAX
                and not missed_facts
                and (not citation_expected or citation >= CITATION_MIN)
            )
        )
    )

    return {
        "answer_match": answer_relevancy,
        "fact_recall": round(len(matched_facts) / max(len(required_facts), 1), 3),
        "fact_precision": round(max(1.0 - hallucination, 0.0), 3),
        "retrieval_hit": context_recall,
        "groundedness": faithfulness,
        "hallucination_score": hallucination,
        "context_precision": precision,
        "citation_score": citation,
        "refusal_correct": refusal_ok,
        "tool_correct": tool_correct,
        "matched_facts": matched_facts,
        "missed_facts": missed_facts,
        "unsupported_claims": unsupported,
        "citations": citations,
        "failure_mode": fail_mode,
        "failure_explanation": documentation_failure_explanation(fail_mode),
        "passed": passed,
    }


def documentation_score_breakdown(result: Any) -> dict[str, float]:
    return {
        "answer_relevancy": round(float(getattr(result, "answer_match", 0.0)), 3),
        "faithfulness": round(float(getattr(result, "groundedness", 0.0)), 3),
        "context_recall": round(float(getattr(result, "retrieval_hit", 0.0)), 3),
        "context_precision": round(float(getattr(result, "context_precision", 0.0)), 3),
        "citation_accuracy": round(float(getattr(result, "citation_score", 0.0)), 3),
    }


def average_documentation_breakdown(results: list[Any]) -> dict[str, float]:
    keys = ["answer_relevancy", "faithfulness", "context_recall", "context_precision", "citation_accuracy"]
    if not results:
        return {key: 0.0 for key in keys}
    breakdowns = [documentation_score_breakdown(result) for result in results]
    return {key: round(sum(item[key] for item in breakdowns) / len(breakdowns), 3) for key in keys}
