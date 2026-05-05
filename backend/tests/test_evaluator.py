from backend.app.evaluator import action_input_score, failure_type, groundedness, hallucination_score, retrieval_hit, score_answer


def test_scorer_gives_credit_for_matching_facts_and_action() -> None:
    facts = ["missing photos", "late submission"]
    answer = "The claim has missing photos and late submission risk."

    answer_match = score_answer(answer, "missing documentation and late submission risk", facts)
    fail = failure_type(answer_match, True, 0.0, answer, facts)

    assert answer_match >= 0.72
    assert fail == "none"


def test_scorer_flags_wrong_action() -> None:
    facts = ["purchase order is missing"]
    answer = "The purchase order is missing."

    fail = failure_type(1.0, False, 0.0, answer, facts)

    assert fail == "wrong_action"


def test_scorer_flags_missed_key_fact() -> None:
    facts = ["purchase order is missing", "emergency fee is unexplained"]
    answer = "The purchase order is missing."

    answer_match = score_answer(answer, "The purchase order is missing and fee is unexplained.", facts)
    fail = failure_type(answer_match, True, 0.0, answer, facts)

    assert fail == "missed_key_fact"


def test_hallucination_flags_unsupported_money() -> None:
    assert hallucination_score("The cost is $99,000.", "The cost is $10,000.") == 1.0



def test_retrieval_and_groundedness_scores() -> None:
    facts = ["missing photos", "late submission"]
    chunks = ["The claim has missing photos and a late submission."]

    assert retrieval_hit(chunks, facts) == 1.0
    assert groundedness("The claim has missing photos.", chunks) > 0.5


def test_action_input_score_uses_expected_terms() -> None:
    score = action_input_score("missing photos and late submission", "request missing claim documents", ["missing photos", "late submission"])

    assert score > 0.2
