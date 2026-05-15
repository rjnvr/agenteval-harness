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

    assert fail == "wrong_tool"


def test_scorer_flags_missed_key_fact() -> None:
    facts = ["purchase order is missing", "emergency fee is unexplained"]
    answer = "The purchase order is missing."

    answer_match = score_answer(answer, "The purchase order is missing and fee is unexplained.", facts)
    fail = failure_type(answer_match, True, 0.0, answer, facts)

    assert fail == "missed_key_fact"


def test_hallucination_flags_unsupported_money() -> None:
    assert hallucination_score("The cost is $99,000.", "The cost is $10,000.") == 1.0


def test_hallucination_allows_supported_paraphrase_and_hyphenation() -> None:
    answer = "Late reporting exceeded the 10-day notice requirement, so coverage cannot be validated yet."
    document = "Reported date was beyond the 10 day notice window. Coverage cannot be confirmed until documentation is supplied."

    assert hallucination_score(answer, document) < 0.45


def test_retrieval_and_groundedness_scores() -> None:
    facts = ["missing photos", "late submission"]
    chunks = ["The claim has missing photos and a late submission."]

    assert retrieval_hit(chunks, facts) == 1.0
    assert groundedness("The claim has missing photos.", chunks) > 0.5


def test_action_input_score_uses_expected_terms() -> None:
    score = action_input_score("missing photos and late submission", "request missing claim documents", ["missing photos", "late submission"])

    assert score > 0.2


def test_failure_taxonomy_distinguishes_common_modes() -> None:
    assert failure_type(1.0, True, 0.0, "", ["missing photos"]) == "premature_stop"
    assert failure_type(1.0, True, 0.0, "ok", ["missing photos"], schema_valid=False) == "schema_invalid"
    assert failure_type(1.0, True, 0.0, "missing photos", ["missing photos"], action_input_score_value=0.0) == "right_tool_wrong_args"
    assert failure_type(1.0, True, 0.0, "missing photos", ["missing photos"], retrieval_hit_value=0.0) == "retrieval_miss"
    assert failure_type(0.1, True, 0.0, "missing photos", ["missing photos"]) == "low_answer_quality"
