from fastapi.testclient import TestClient

from backend.app.main import app


def test_cases_endpoint_returns_seeded_cases() -> None:
    with TestClient(app) as client:
        response = client.get("/api/cases")

    assert response.status_code == 200
    assert len(response.json()) == 20


def test_mock_run_and_summary() -> None:
    with TestClient(app) as client:
        run_response = client.post("/api/runs", json={"mode": "mock"})
        summary_response = client.get("/api/summary")

    assert run_response.status_code == 200
    run = run_response.json()
    assert run["total_cases"] == 20
    assert run["mode"] == "mock"
    assert len(run["results"]) == 20
    first_result = run["results"][0]
    assert first_result["matched_facts"]
    assert first_result["missed_facts"] == []
    assert set(first_result["matched_facts"]) == set(first_result["expected_facts"])
    assert summary_response.status_code == 200
    assert summary_response.json()["total_tests_run"] >= 20


def test_run_detail_endpoint() -> None:
    with TestClient(app) as client:
        created = client.post("/api/runs", json={"mode": "mock"}).json()
        detail = client.get(f"/api/runs/{created['id']}")

    assert detail.status_code == 200
    assert detail.json()["id"] == created["id"]

