import re
from dataclasses import dataclass
from typing import Any


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ACCOUNT_RE = re.compile(r"\b(?:ACCT|ACCOUNT|POLICY|CLAIM|CLM|INV|PO)[-:\s](?=[A-Z0-9-]*\d)[A-Z0-9-]{3,}\b", re.IGNORECASE)
CONTACT_RE = re.compile(r"\b(?:Policyholder|Customer|Contact|Owner|Manager):\s*[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,2}\b")

REDACTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", EMAIL_RE),
    ("phone", PHONE_RE),
    ("ssn", SSN_RE),
    ("account_id", ACCOUNT_RE),
    ("contact_name", CONTACT_RE),
)


@dataclass(frozen=True)
class RedactionReport:
    redacted_text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact_text(text: str) -> RedactionReport:
    counts: dict[str, int] = {}
    redacted = text
    for label, pattern in REDACTION_PATTERNS:
        redacted, count = pattern.subn(f"[REDACTED_{label.upper()}]", redacted)
        if count:
            counts[label] = count
    return RedactionReport(redacted_text=redacted, counts=counts)


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value).redacted_text
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def measure_recall(samples: list[dict[str, object]]) -> dict[str, object]:
    expected_total = 0
    redacted_total = 0
    by_type: dict[str, dict[str, int | float]] = {}
    for sample in samples:
        text = str(sample["text"])
        expected = dict(sample.get("expected", {}))
        report = redact_text(text)
        for label, expected_count in expected.items():
            expected_int = int(expected_count)
            found = min(report.counts.get(str(label), 0), expected_int)
            expected_total += expected_int
            redacted_total += found
            bucket = by_type.setdefault(str(label), {"expected": 0, "redacted": 0, "recall": 0.0})
            bucket["expected"] = int(bucket["expected"]) + expected_int
            bucket["redacted"] = int(bucket["redacted"]) + found

    for bucket in by_type.values():
        expected = int(bucket["expected"])
        bucket["recall"] = round(int(bucket["redacted"]) / max(expected, 1), 3)

    return {
        "expected_entities": expected_total,
        "redacted_entities": redacted_total,
        "recall": round(redacted_total / max(expected_total, 1), 3),
        "by_type": by_type,
    }
