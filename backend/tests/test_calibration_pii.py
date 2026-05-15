from backend.app.calibration import calibration_summary, cohens_kappa, percent_agreement
from backend.app.pii import measure_recall, redact_text, redact_value


def test_percent_agreement_and_kappa() -> None:
    assert percent_agreement([True, False], [True, False]) == 1.0
    assert cohens_kappa([True, True, False, False], [True, False, True, False]) == 0.0
    assert cohens_kappa([True, False, True, False], [True, False, True, False]) == 1.0


def test_calibration_summary_uses_judge_threshold_and_failure_modes() -> None:
    labels = [
        {"human_passed": True, "human_failure_mode": "none", "judge_score": 0.9, "judge_failure_mode": "none"},
        {"human_passed": False, "human_failure_mode": "wrong_tool", "judge_score": 0.4, "judge_failure_mode": "wrong_tool"},
        {"human_passed": False, "human_failure_mode": "missed_key_fact", "judge_score": 0.8, "judge_failure_mode": "none"},
    ]

    summary = calibration_summary(labels)

    assert summary["sample_size"] == 3
    assert summary["pass_agreement"] == 0.667
    assert summary["failure_mode_agreement"] == 0.667


def test_redacts_nested_trace_values_and_measures_recall() -> None:
    trace = redact_value({"chunk": "Contact: Jane Ramos at jane@example.com or 415-555-0199 for CLM-7788."})

    assert "jane@example.com" not in trace["chunk"]
    assert "415-555-0199" not in trace["chunk"]
    assert "CLM-7788" not in trace["chunk"]
    assert "claim has" in redact_text("The claim has missing documentation.").redacted_text
    assert redact_text("SSN 123-45-6789").counts["ssn"] == 1

    recall = measure_recall(
        [{"text": "Customer: Alex Chen, alex@example.com, 212-555-0199, SSN 123-45-6789.", "expected": {"contact_name": 1, "email": 1, "phone": 1, "ssn": 1}}]
    )
    assert recall["recall"] == 1.0
