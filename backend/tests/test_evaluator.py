from backend.app.evaluator import (
    action_input_score,
    failure_type,
    groundedness,
    hallucination_score,
    preference_score,
    retrieval_hit,
    score_answer,
    slot_valid,
    timezone_correct,
)


def test_scorer_gives_credit_for_matching_considerations_and_action() -> None:
    facts = ["John avoids peer calls before 08:00", "all attendees are free at 10:00 Pacific"]
    answer = "John avoids peer calls before 08:00, and all attendees are free at 10:00 Pacific."

    answer_match = score_answer(answer, "Propose 10:00 Pacific.", facts)
    fail = failure_type(answer_match, True, 0.0, answer, facts, action="propose_times", expected_action="propose_times")

    assert answer_match >= 0.72
    assert fail == "none"


def test_scorer_flags_wrong_action() -> None:
    facts = ["Leo has not shared availability"]
    answer = "Leo has not shared availability."

    fail = failure_type(1.0, False, 0.0, answer, facts, action="book_meeting", expected_action="request_availability")

    assert fail == "no_followup"


def test_scorer_flags_missed_key_fact() -> None:
    facts = ["Sarah is busy at 10:00 Pacific", "all attendees are free at 11:00 Pacific"]
    answer = "Sarah is busy at 10:00 Pacific."

    answer_match = score_answer(answer, "Book 11:00 Pacific.", facts)
    fail = failure_type(answer_match, True, 0.0, answer, facts, action="book_meeting", expected_action="book_meeting")

    assert fail == "missed_key_fact"


def test_hallucination_flags_unsupported_slot_text() -> None:
    assert hallucination_score("Book 4:00 PM with CalendlyRoom.", "Book 3:00 PM with Zoom.") >= 0.45


def test_retrieval_and_groundedness_scores() -> None:
    facts = ["John avoids peer calls before 08:00", "all attendees are free at 10:00 Pacific"]
    chunks = ["John avoids peer calls before 08:00. All attendees are free at 10:00 Pacific."]

    assert retrieval_hit(chunks, facts) == 1.0
    assert groundedness("John avoids peer calls before 08:00.", chunks) > 0.5


def test_action_input_score_uses_expected_terms() -> None:
    score = action_input_score(
        "10:00 Pacific because John avoids early peer calls",
        "Propose 10:00 Pacific",
        ["John avoids peer calls before 08:00", "all attendees are free at 10:00 Pacific"],
    )

    assert score > 0.2


def test_slot_valid_checks_busy_blocks_and_working_hours() -> None:
    participants = [
        {
            "name": "Sarah",
            "timezone": "America/Los_Angeles",
            "working_hours": {"start": "09:00", "end": "17:00"},
            "availability_known": True,
            "busy_blocks": [{"start": "2026-06-12T10:00:00-07:00", "end": "2026-06-12T10:30:00-07:00"}],
        }
    ]

    assert slot_valid('{"start":"2026-06-12T11:00:00-07:00","end":"2026-06-12T11:30:00-07:00"}', participants)
    assert not slot_valid('{"start":"2026-06-12T10:00:00-07:00","end":"2026-06-12T10:30:00-07:00"}', participants)
    assert not slot_valid('{"start":"2026-06-12T18:00:00-07:00","end":"2026-06-12T18:30:00-07:00"}', participants)


def test_preference_score_catches_peer_early_call_trap() -> None:
    context = {
        "request": {"meeting_with_seniority": "peer"},
        "participants": [{"name": "John", "timezone": "America/Los_Angeles"}],
        "preference_rules": [{"type": "no_early_unless_seniority", "person": "John", "before": "08:00", "allowed_seniority": ["CEO"]}],
    }

    assert preference_score('{"start":"2026-06-10T07:00:00-07:00","end":"2026-06-10T07:30:00-07:00"}', "book_meeting", context, "propose_times") == 0
    assert preference_score('{"start":"2026-06-10T10:00:00-07:00","end":"2026-06-10T10:30:00-07:00"}', "book_meeting", context, "propose_times") == 1


def test_timezone_correct_compares_expected_instant() -> None:
    expected = {"slot": {"start": "2026-06-11T09:00:00-07:00", "end": "2026-06-11T09:30:00-07:00"}}

    assert timezone_correct('{"start":"2026-06-11T09:00:00-07:00","end":"2026-06-11T09:30:00-07:00"}', expected, "propose_times")
    assert not timezone_correct('{"start":"2026-06-11T09:00:00+01:00","end":"2026-06-11T09:30:00+01:00"}', expected, "propose_times")


def test_failure_taxonomy_prioritizes_scheduling_modes() -> None:
    assert failure_type(1.0, True, 0.0, "ok", ["x"], schema_valid=False) == "schema_invalid"
    assert failure_type(1.0, True, 0.0, "ok", ["x"], slot_valid_value=False, action="book_meeting", expected_action="book_meeting") == "double_booking"
    assert failure_type(1.0, True, 0.0, "ok", ["x"], preference_score_value=0.0, action="book_meeting", expected_action="book_meeting") == "preference_violation"
    assert failure_type(1.0, True, 0.0, "ok", ["x"], timezone_correct_value=False, action="book_meeting", expected_action="book_meeting") == "timezone_error"
    assert failure_type(1.0, True, 0.0, "ok", ["x"], action="book_meeting", expected_action="request_availability") == "no_followup"
    assert failure_type(0.1, True, 0.0, "x", ["x"], action="book_meeting", expected_action="book_meeting") == "low_answer_quality"
