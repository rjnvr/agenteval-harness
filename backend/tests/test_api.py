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
    assert set(first_result["matched_facts"]) == set(first_result["expected_facts"])
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
    assert result["schema_valid"] is False


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
