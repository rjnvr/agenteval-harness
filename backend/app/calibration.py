PASS_THRESHOLD = 0.72


def pass_bucket(score: float | None, threshold: float = PASS_THRESHOLD) -> bool:
    return score is not None and score >= threshold


def percent_agreement(expected: list[object], observed: list[object]) -> float:
    if len(expected) != len(observed):
        raise ValueError("expected and observed labels must have the same length")
    if not expected:
        return 0.0
    matches = sum(1 for left, right in zip(expected, observed, strict=True) if left == right)
    return round(matches / len(expected), 3)


def cohens_kappa(expected: list[bool], observed: list[bool]) -> float:
    if len(expected) != len(observed):
        raise ValueError("expected and observed labels must have the same length")
    if not expected:
        return 0.0

    observed_agreement = percent_agreement(list(expected), list(observed))
    expected_true = sum(expected) / len(expected)
    expected_false = 1 - expected_true
    observed_true = sum(observed) / len(observed)
    observed_false = 1 - observed_true
    chance_agreement = (expected_true * observed_true) + (expected_false * observed_false)
    if chance_agreement == 1:
        return 1.0 if observed_agreement == 1 else 0.0
    return round((observed_agreement - chance_agreement) / (1 - chance_agreement), 3)


def calibration_summary(labels: list[dict[str, object]], threshold: float = PASS_THRESHOLD) -> dict[str, object]:
    comparable = [label for label in labels if label.get("judge_score") is not None]
    human_pass = [bool(label["human_passed"]) for label in comparable]
    judge_pass = [pass_bucket(float(label["judge_score"]), threshold) for label in comparable]
    human_modes = [str(label["human_failure_mode"]) for label in comparable]
    judge_modes = [str(label.get("judge_failure_mode", "none")) for label in comparable]

    return {
        "sample_size": len(comparable),
        "threshold": threshold,
        "pass_agreement": percent_agreement(list(human_pass), list(judge_pass)) if comparable else 0.0,
        "pass_kappa": cohens_kappa(human_pass, judge_pass) if comparable else 0.0,
        "failure_mode_agreement": percent_agreement(human_modes, judge_modes) if comparable else 0.0,
    }
