from fastapi.testclient import TestClient

from backend.app.main import app


def test_cases_endpoint_returns_seeded_cases() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases")

    assert response.status_code == 200
    assert len(response.json()) == 20


def test_mock_run_and_summary() -> None:
    with TestClient(app) as client:
        run_response = client.post("/api/runs", json={"provider": "mock"})
        summary_response = client.get("/api/summary")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["total_cases"] == 20
    assert run["provider"] == "mock"
    assert run["model"] == "mock-deterministic"
    assert len(run["results"]) == 20
    first_result = run["results"][0]
    assert first_result["matched_facts"]
    assert first_result["missed_facts"] == []
    assert first_result["fact_recall"] == 1.0
    assert first_result["retrieval_hit"] >= 0.5
    assert first_result["schema_valid"] is True
    assert "unsupported_claims" in first_result
    assert first_result["failure_mode"] == first_result["failure_type"]
    assert "failure_explanation" in first_result
    assert "trace" in first_result
    assert "score_breakdown" in first_result
    assert first_result["score_breakdown"]["semantic_quality"] >= 0
    assert "calibration" in summary_response.json()
    assert "pii_redaction" in summary_response.json()
    assert "score_breakdown" in summary_response.json()
    assert set(first_result["matched_facts"]) == set(first_result["required_facts"])
    assert first_result["acceptable_actions"]
    assert summary_response.status_code == 200
    assert summary_response.json()["total_tests_run"] >= 20


def test_run_detail_endpoint() -> None:
    with TestClient(app) as client:
        created = client.post("/api/runs", json={"provider": "mock"}).json()
        detail = client.get(f"/api/runs/{created['id']}")

    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]
    assert "action_input_score" in detail.json()["results"][0]


def test_selected_cases_are_supported() -> None:
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"provider": "mock", "case_ids": ["case_001", "case_002"]})

    assert response.status_code == 200
    body = response.json()
    assert body["total_cases"] == 2
    assert {result["case_id"] for result in body["results"]} == {"case_001", "case_002"}


def test_openai_missing_key_returns_agent_error() -> None:
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"provider": "openai", "case_ids": ["case_001"]})

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["failure_type"] == "agent_error"
    assert result["failure_mode"] == "agent_error"
    assert result["schema_valid"] is False


def test_live_providers_require_per_run_key_even_if_env_exists(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-key-that-must-not-be-used")

    with TestClient(app) as client:
        response = client.post("/api/runs", json={"provider": "anthropic", "case_ids": ["case_001"]})

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["failure_type"] == "agent_error"
    assert "requires an API key" in result["answer"]


def test_google_and_openrouter_modes_are_supported_without_storing_keys() -> None:
    with TestClient(app) as client:
        google = client.post("/api/runs", json={"provider": "google", "case_ids": ["case_001"]})
        llama = client.post("/api/runs", json={"provider": "llama", "case_ids": ["case_001"]})

    assert google.status_code == 200
    assert google.json()["provider"] == "google"
    assert google.json()["results"][0]["failure_type"] == "agent_error"
    assert llama.status_code == 200
    assert llama.json()["provider"] == "openrouter"
    assert llama.json()["results"][0]["failure_type"] == "agent_error"


def test_calibration_and_pii_endpoints() -> None:
    with TestClient(app) as client:
        calibration = client.get("/api/calibration")
        pii = client.get("/api/pii-redaction")

    assert calibration.status_code == 200
    assert calibration.json()["sample_size"] >= 10
    assert "pass_kappa" in calibration.json()
    assert pii.status_code == 200
    assert pii.json()["recall"] >= 0.9


def test_comparison_endpoint_returns_run_metrics() -> None:
    with TestClient(app) as client:
        created = client.post("/api/runs", json={"provider": "mock", "case_ids": ["case_001", "case_002"]})
        comparison = client.get("/api/comparison")

    assert created.status_code == 200
    assert comparison.status_code == 200
    runs = comparison.json()["runs"]
    assert runs
    latest = runs[0]
    assert "avg_answer_match" in latest
    assert "avg_fact_recall" in latest
    assert "strict_pass_rate" in latest
    assert "score_breakdown" in latest
    assert "avg_semantic_quality" in latest
    assert "avg_tool_accuracy" in latest
    assert "failure_counts" in latest


def test_latest_run_summary_uses_request_provider() -> None:
    with TestClient(app) as client:
        created = client.post("/api/runs", json={"provider": "mock", "case_ids": ["case_001"]})
        summary = client.post("/api/runs/latest/summary", json={"provider": "mock"})

    assert created.status_code == 200
    assert summary.status_code == 200
    body = summary.json()
    assert body["run_id"] == created.json()["id"]
    assert body["provider"] == "mock"
    assert "latest run covered" in body["summary"]
    assert "Quality signals" in body["summary"]
    assert "score_breakdown" in body["report"]
    assert body["report"]["cases"]


def test_legacy_mode_shape_still_works() -> None:
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"mode": "mock", "case_ids": ["case_001"]})

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_per_run_key_takes_precedence(monkeypatch) -> None:
    from backend.app.agents import AgentOutput
    import backend.app.runner as runner

    seen = {}

    def fake_openai_agent(case, document_text, model, api_key):
        seen["api_key"] = api_key
        facts = ["missing photos", "late submission"]
        return AgentOutput(
            answer=f"{case.expected_answer} Key facts: {', '.join(facts)}.",
            action=case.expected_action,
            action_input=", ".join(facts),
            retrieved_chunks=[document_text],
            latency_ms=1,
            cost_usd=0.0,
        )

    monkeypatch.setattr(runner, "run_openai_agent", fake_openai_agent)
    with TestClient(app) as client:
        response = client.post(
            "/api/runs",
            json={"provider": "openai", "api_key": "per-run-redacted", "case_ids": ["case_001"]},
        )

    assert response.status_code == 200
    assert seen["api_key"] == "per-run-redacted"
