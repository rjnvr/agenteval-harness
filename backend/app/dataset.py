import json
from pathlib import Path
from sqlalchemy.orm import Session

from backend.app.models import Document, EvalCase

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
