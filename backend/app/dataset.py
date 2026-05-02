import json
from pathlib import Path
from sqlalchemy.orm import Session

from backend.app.models import Document, EvalCase

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "seed_cases.json"


def load_seed_data() -> dict[str, list[dict[str, object]]]:
    with DATA_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def seed_database(db: Session) -> None:
    if db.query(EvalCase).count() > 0:
        return
    seed = load_seed_data()
    for item in seed["documents"]:
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
        db.add(
            EvalCase(
                id=str(item["id"]),
                document_id=str(item["document_id"]),
                input=str(item["input"]),
                expected_answer=str(item["expected_answer"]),
                expected_facts_json=json.dumps(item["expected_facts"]),
                expected_action=str(item["expected_action"]),
            )
        )
    db.commit()


def expected_facts(case: EvalCase) -> list[str]:
    return list(json.loads(case.expected_facts_json))

