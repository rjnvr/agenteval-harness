import json
from pathlib import Path
from sqlalchemy.orm import Session

from backend.app.models import Document, EvalCase, EvalResult

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "seed_cases.json"
HUMAN_LABELS_FILE = Path(__file__).resolve().parents[2] / "data" / "human_judge_labels.json"
PII_SAMPLES_FILE = Path(__file__).resolve().parents[2] / "data" / "pii_redaction_samples.json"


def load_seed_data() -> dict[str, list[dict[str, object]]]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_human_judge_labels() -> list[dict[str, object]]:
    with HUMAN_LABELS_FILE.open("r", encoding="utf-8") as file:
        return list(json.load(file))


def load_pii_samples() -> list[dict[str, object]]:
    with PII_SAMPLES_FILE.open("r", encoding="utf-8") as file:
        return list(json.load(file))


def seed_database(db: Session) -> None:
    seed = load_seed_data()
    for item in seed["documents"]:
        document = db.get(Document, str(item["id"]))
        if document:
            document.name = str(item["name"])
            document.category = str(item["category"])
            document.text = str(item["text"])
        else:
            db.add(
                Document(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    category=str(item["category"]),
                    text=str(item["text"]),
                )
            )
    db.flush()
    for item in seed["cases"]:
        case = db.get(EvalCase, str(item["id"]))
        values = {
            "document_id": str(item["document_id"]),
            "input": str(item["input"]),
            "expected_answer": str(item["expected_answer"]),
            "expected_facts_json": json.dumps(item["expected_facts"]),
            "expected_action": str(item["expected_action"]),
            "acceptable_actions_json": json.dumps(item.get("acceptable_actions", [item["expected_action"]])),
            "context_json": json.dumps(item.get("context", {})),
            "expected_decision_json": json.dumps(item.get("expected_decision", {})),
        }
        if case:
            for name, value in values.items():
                setattr(case, name, value)
        else:
            db.add(
                EvalCase(
                    id=str(item["id"]),
                    **values,
                )
            )
    db.commit()


def upsert_cases(
    db: Session,
    documents: list[dict[str, object]],
    cases: list[dict[str, object]],
    replace: bool = False,
) -> tuple[int, int]:
    if replace:
        db.query(EvalResult).delete()
        db.query(EvalCase).delete()
        db.query(Document).delete()
        db.flush()

    known_doc_ids = {doc.id for doc in db.query(Document.id).all()} | {str(d["id"]) for d in documents}
    for case in cases:
        if str(case["document_id"]) not in known_doc_ids:
            raise ValueError(f"Case {case['id']} references unknown document_id {case['document_id']}")

    doc_count = 0
    for item in documents:
        document = db.get(Document, str(item["id"]))
        if document:
            document.name = str(item["name"])
            document.category = str(item["category"])
            document.text = str(item["text"])
        else:
            db.add(
                Document(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    category=str(item["category"]),
                    text=str(item["text"]),
                )
            )
        doc_count += 1
    db.flush()

    case_count = 0
    for item in cases:
        values = {
            "document_id": str(item["document_id"]),
            "input": str(item["input"]),
            "expected_answer": str(item["expected_answer"]),
            "expected_facts_json": json.dumps(item["expected_facts"]),
            "expected_action": str(item["expected_action"]),
            "acceptable_actions_json": json.dumps(
                item.get("acceptable_actions") or [item["expected_action"]]
            ),
            "context_json": json.dumps(item.get("context", {})),
            "expected_decision_json": json.dumps(item.get("expected_decision", {})),
        }
        case = db.get(EvalCase, str(item["id"]))
        if case:
            for name, value in values.items():
                setattr(case, name, value)
        else:
            db.add(EvalCase(id=str(item["id"]), **values))
        case_count += 1
    db.commit()
    return doc_count, case_count


def expected_facts(case: EvalCase) -> list[str]:
    return list(json.loads(case.expected_facts_json))


def required_facts(case: EvalCase) -> list[str]:
    facts = expected_facts(case)
    if facts and isinstance(facts[0], dict):
        return [str(item["text"]) for item in facts if item.get("required", True)]
    return facts


def supporting_facts(case: EvalCase) -> list[str]:
    facts = expected_facts(case)
    if facts and isinstance(facts[0], dict):
        return [str(item["text"]) for item in facts if not item.get("required", True)]
    return []


def all_fact_texts(case: EvalCase) -> list[str]:
    facts = expected_facts(case)
    if facts and isinstance(facts[0], dict):
        return [str(item["text"]) for item in facts]
    return facts


def acceptable_actions(case: EvalCase) -> list[str]:
    if hasattr(case, "acceptable_actions_json") and case.acceptable_actions_json:
        actions = list(json.loads(case.acceptable_actions_json))
        if actions:
            return actions
    return [case.expected_action]


def case_context(case: EvalCase) -> dict[str, object]:
    raw = getattr(case, "context_json", "") or "{}"
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def expected_decision(case: EvalCase) -> dict[str, object]:
    raw = getattr(case, "expected_decision_json", "") or "{}"
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def context_lines(case: EvalCase) -> list[str]:
    context = case_context(case)
    document = getattr(case, "document", None)
    document_text = str(getattr(document, "text", ""))
    lines: list[str] = [document_text] if document_text else []
    request = context.get("request")
    if isinstance(request, dict):
        lines.append(
            "Request: "
            + ", ".join(f"{key}={value}" for key, value in request.items() if value not in (None, "", []))
        )

    participants = context.get("participants")
    if isinstance(participants, list):
        for participant in participants:
            if not isinstance(participant, dict):
                continue
            name = str(participant.get("name", "Unknown"))
            role = str(participant.get("role", participant.get("seniority", "participant")))
            timezone = str(participant.get("timezone", "unknown timezone"))
            working_hours = participant.get("working_hours", {})
            hours = ""
            if isinstance(working_hours, dict):
                hours = f"{working_hours.get('start', '?')}-{working_hours.get('end', '?')}"
            known = participant.get("availability_known", True)
            lines.append(f"Participant: {name}; role={role}; timezone={timezone}; working_hours={hours}; availability_known={known}.")
            busy_blocks = participant.get("busy_blocks", [])
            if isinstance(busy_blocks, list):
                for block in busy_blocks:
                    if isinstance(block, dict):
                        lines.append(f"Busy: {name} {block.get('start')} to {block.get('end')}.")
            preferences = participant.get("preferences", [])
            if isinstance(preferences, list):
                for preference in preferences:
                    lines.append(f"Preference: {name} {preference}.")

    rules = context.get("preference_rules")
    if isinstance(rules, list):
        for rule in rules:
            if isinstance(rule, dict):
                lines.append("Preference rule: " + json.dumps(rule, sort_keys=True))

    constraints = context.get("constraints")
    if isinstance(constraints, dict):
        lines.append("Constraints: " + json.dumps(constraints, sort_keys=True))

    expected = expected_decision(case)
    if expected:
        lines.append("Expected decision: " + json.dumps(expected, sort_keys=True))
    return lines or [document_text]


def preference_rules(case: EvalCase) -> list[dict[str, object]]:
    rules = case_context(case).get("preference_rules", [])
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]
