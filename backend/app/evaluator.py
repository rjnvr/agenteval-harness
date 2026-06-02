import re
from collections import Counter
from datetime import datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.rag import tokenize
from backend.app.tools import SLOT_ACTIONS

FAILURE_MODES = {
    "wrong_action",
    "double_booking",
    "outside_working_hours",
    "preference_violation",
    "timezone_error",
    "missed_participant",
    "premature_booking",
    "no_followup",
    "unsupported_availability",
    "missed_key_fact",
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
    "attendee",
    "attendees",
    "available",
    "availability",
    "because",
    "before",
    "book",
    "booking",
    "calendar",
    "cannot",
    "call",
    "coordinate",
    "coordinated",
    "decline",
    "expected",
    "facts",
    "follow",
    "information",
    "insufficient",
    "meeting",
    "missing",
    "participant",
    "participants",
    "preference",
    "propose",
    "proposing",
    "request",
    "respects",
    "reschedule",
    "required",
    "requirement",
    "slot",
    "should",
    "status",
    "timezone",
    "working",
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


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _parse_clock(value: object) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        hour, minute = value.split(":", 1)
        return time(hour=int(hour), minute=int(minute[:2]))
    except (ValueError, TypeError):
        return None


def parse_slot(proposed_slot: object) -> tuple[datetime, datetime] | None:
    if isinstance(proposed_slot, dict):
        start = _parse_dt(proposed_slot.get("start"))
        end = _parse_dt(proposed_slot.get("end"))
        if start and end and end > start:
            return start, end
        return None
    if not isinstance(proposed_slot, str) or not proposed_slot.strip():
        return None
    raw = proposed_slot.strip()
    try:
        import json

        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parse_slot(parsed)
    if "/" in raw:
        start_raw, end_raw = raw.split("/", 1)
    elif " to " in raw:
        start_raw, end_raw = raw.split(" to ", 1)
    else:
        return None
    start = _parse_dt(start_raw)
    end = _parse_dt(end_raw)
    if start and end and end > start:
        return start, end
    return None


def _participant_zone(participant: dict[str, object]) -> ZoneInfo | None:
    timezone = participant.get("timezone")
    if not isinstance(timezone, str):
        return None
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return None


def _within_working_hours(start: datetime, end: datetime, participant: dict[str, object]) -> bool:
    zone = _participant_zone(participant)
    if zone is None:
        return False
    local_start = start.astimezone(zone)
    local_end = end.astimezone(zone)
    if local_start.date() != local_end.date():
        return False
    hours = participant.get("working_hours")
    if not isinstance(hours, dict):
        return True
    day_start = _parse_clock(hours.get("start"))
    day_end = _parse_clock(hours.get("end"))
    if day_start is None or day_end is None:
        return True
    return day_start <= local_start.time() and local_end.time() <= day_end


def _overlaps(left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return left_start < right_end and right_start < left_end


def slot_valid(proposed_slot: object, participants: list[dict[str, object]], action: str = "book_meeting") -> bool:
    if action not in SLOT_ACTIONS:
        return True
    slot = parse_slot(proposed_slot)
    if slot is None:
        return False
    start, end = slot
    for participant in participants:
        if participant.get("availability_known", True) is False:
            return False
        if not _within_working_hours(start, end, participant):
            return False
        busy_blocks = participant.get("busy_blocks", [])
        if not isinstance(busy_blocks, list):
            continue
        for block in busy_blocks:
            if not isinstance(block, dict):
                continue
            busy_start = _parse_dt(block.get("start"))
            busy_end = _parse_dt(block.get("end"))
            if busy_start and busy_end and _overlaps(start, end, busy_start, busy_end):
                return False
    return True


def _request_seniority(context: dict[str, object]) -> str:
    request = context.get("request")
    if isinstance(request, dict):
        value = request.get("meeting_with_seniority") or request.get("counterparty_seniority")
        if value is not None:
            return str(value).lower()
    return ""


def preference_score(
    proposed_slot: object,
    action: str,
    context: dict[str, object],
    expected_action: str | None = None,
) -> float:
    rules = context.get("preference_rules", [])
    if not isinstance(rules, list) or not rules:
        return 1.0
    slot = parse_slot(proposed_slot)
    honored = 0
    checked = 0
    participants = context.get("participants", [])
    participant_by_name = {
        str(item.get("name")): item
        for item in participants
        if isinstance(item, dict) and item.get("name") is not None
    } if isinstance(participants, list) else {}

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_type = str(rule.get("type", ""))
        checked += 1

        if rule_type == "require_availability_before_booking":
            honored += int(action == "request_availability" if expected_action == "request_availability" else action not in SLOT_ACTIONS)
            continue

        if action not in SLOT_ACTIONS:
            honored += 1
            continue
        if slot is None:
            continue
        start, _end = slot
        person = str(rule.get("person", ""))
        participant = participant_by_name.get(person)
        zone = _participant_zone(participant) if isinstance(participant, dict) else None
        local_start = start.astimezone(zone) if zone else start

        if rule_type == "no_early_unless_seniority":
            before = _parse_clock(rule.get("before")) or time(8, 0)
            allowed = {str(item).lower() for item in rule.get("allowed_seniority", []) if item is not None} if isinstance(rule.get("allowed_seniority"), list) else set()
            seniority = _request_seniority(context)
            violates = local_start.time() < before and seniority not in allowed
            honored += int(not violates)
        elif rule_type == "no_calls_before":
            before = _parse_clock(rule.get("before")) or time(8, 0)
            honored += int(local_start.time() >= before)
        elif rule_type == "no_calls_after":
            after = _parse_clock(rule.get("after")) or time(17, 0)
            honored += int(local_start.time() < after)
        elif rule_type == "avoid_day":
            day = str(rule.get("day", "")).lower()
            honored += int(local_start.strftime("%A").lower() != day)
        elif rule_type == "no_lunch":
            start_after = _parse_clock(rule.get("start")) or time(12, 0)
            end_before = _parse_clock(rule.get("end")) or time(13, 0)
            honored += int(not (start_after <= local_start.time() < end_before))
        else:
            honored += 1

    return round(honored / max(checked, 1), 3)


def timezone_correct(proposed_slot: object, expected_decision: dict[str, object], action: str) -> bool:
    if action not in SLOT_ACTIONS:
        return True
    slot = parse_slot(proposed_slot)
    if slot is None:
        return False
    expected_slot = expected_decision.get("slot")
    if not isinstance(expected_slot, dict):
        return True
    expected = parse_slot(expected_slot)
    if expected is None:
        return True
    start, end = slot
    expected_start, expected_end = expected
    return start.astimezone(ZoneInfo("UTC")) == expected_start.astimezone(ZoneInfo("UTC")) and end.astimezone(ZoneInfo("UTC")) == expected_end.astimezone(ZoneInfo("UTC"))


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
    agent_failed: bool = False,
    slot_valid_value: bool = True,
    preference_score_value: float = 1.0,
    timezone_correct_value: bool = True,
    action: str = "",
    expected_action: str = "",
    context: dict[str, object] | None = None,
) -> str:
    context = context or {}
    if not schema_valid:
        return "schema_invalid"
    if agent_failed:
        return "agent_error"
    if not answer.strip():
        return "premature_booking" if action in SLOT_ACTIONS else "no_followup"
    if not slot_valid_value and action in SLOT_ACTIONS:
        participants = context.get("participants", [])
        if isinstance(participants, list):
            for participant in participants:
                if isinstance(participant, dict) and participant.get("availability_known", True) is False:
                    return "premature_booking"
        return "double_booking"
    if preference_score_value < 1.0:
        return "preference_violation"
    if not timezone_correct_value:
        return "timezone_error"
    if expected_action == "request_availability" and action != "request_availability":
        return "no_followup"
    if expected_action in SLOT_ACTIONS and action == "request_availability":
        return "missed_participant"
    if expected_action not in SLOT_ACTIONS and action in SLOT_ACTIONS:
        return "premature_booking"
    if hallucination >= 0.45:
        return "unsupported_availability"
    if groundedness_value < 0.45:
        return "unsupported_availability"
    if not tool_correct:
        return "wrong_action"
    answer_terms = tokenize(answer)
    if retrieval_hit_value < 0.3:
        return "missed_participant"
    if any(not (tokenize(fact) <= answer_terms or fact.lower() in answer.lower()) for fact in expected_facts):
        return "missed_key_fact"
    if action_input_score_value < 0.12:
        return "unsupported_availability"
    if answer_match < 0.72:
        return "low_answer_quality"
    return "none"


def failure_explanation(mode: str) -> str:
    explanations = {
        "wrong_action": "Agent selected the wrong scheduling decision.",
        "double_booking": "Agent proposed a slot that conflicts with a participant's calendar or working hours.",
        "outside_working_hours": "Agent proposed a slot outside a participant's working hours.",
        "preference_violation": "Agent ignored a contextual scheduling preference.",
        "timezone_error": "Agent converted or represented the slot in the wrong timezone.",
        "missed_participant": "Agent missed a participant, calendar, or required coordination consideration.",
        "premature_booking": "Agent booked or proposed a time before it had enough availability context.",
        "no_followup": "Agent should have requested availability or followed up, but did not.",
        "unsupported_availability": "Agent claimed availability or slot support not grounded in the assembled context.",
        "missed_key_fact": "Agent missed one or more expected coordination considerations.",
        "schema_invalid": "Agent output did not satisfy the expected response schema.",
        "agent_error": "Agent call failed before a valid response could be scored.",
        "low_answer_quality": "Agent response had low semantic overlap with the expected coordination decision.",
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
    decision_correctness = 1.0 if getattr(result, "tool_correct") else 0.0
    slot_score = 1.0 if getattr(result, "slot_valid", True) else 0.0
    grounded = float(getattr(result, "groundedness"))
    constraint_satisfaction = round((slot_score * 0.7) + (grounded * 0.3), 3)
    preference_adherence = float(getattr(result, "preference_score", 1.0))
    timezone_accuracy = 1.0 if getattr(result, "timezone_correct", True) else 0.0
    coverage = float(getattr(result, "fact_recall"))
    return {
        "decision_correctness": round(decision_correctness, 3),
        "constraint_satisfaction": constraint_satisfaction,
        "preference_adherence": round(preference_adherence, 3),
        "timezone_accuracy": round(timezone_accuracy, 3),
        "coordination_coverage": round(coverage, 3),
    }


def average_score_breakdown(results: list[object]) -> dict[str, float]:
    if not results:
        return {
            "decision_correctness": 0.0,
            "constraint_satisfaction": 0.0,
            "preference_adherence": 0.0,
            "timezone_accuracy": 0.0,
            "coordination_coverage": 0.0,
        }
    breakdowns = [score_breakdown(result) for result in results]
    return {
        key: round(sum(item[key] for item in breakdowns) / len(breakdowns), 3)
        for key in breakdowns[0]
    }
