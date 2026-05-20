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


def test_async_run_can_be_polled_for_status() -> None:
    with TestClient(app) as client:
        created = client.post("/api/runs", json={"provider": "mock", "case_ids": ["case_001"], "async_run": True})
        status = client.get(f"/api/runs/{created.json()['id']}/status")

    assert created.status_code == 200
    assert status.status_code == 200
    body = status.json()
    assert body["status"] in {"queued", "running", "completed"}
    assert body["total_cases"] == 1
    if body["status"] == "completed":
        assert len(body["results"]) == 1


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


def test_webhook_provider_requires_url() -> None:
    with TestClient(app) as client:
        response = client.post("/api/runs", json={"provider": "webhook", "case_ids": ["case_001"]})

    assert response.status_code == 400
    assert "webhook_url" in response.json()["detail"]


def test_webhook_provider_calls_user_endpoint(monkeypatch) -> None:
    from backend.app.agents import AgentOutput
    import backend.app.runner as runner

    seen = {}

    def fake_webhook_agent(case, document_text, webhook_url, webhook_headers):
        seen["url"] = webhook_url
        seen["headers"] = webhook_headers
        seen["case_id"] = case.id
        facts = ["missing photos", "late submission"]
        return AgentOutput(
            answer=f"{case.expected_answer} Key facts: {', '.join(facts)}.",
            action=case.expected_action,
            action_input=", ".join(facts),
            retrieved_chunks=[document_text[:200]],
            latency_ms=42,
            cost_usd=0.0021,
        )

    monkeypatch.setattr(runner, "run_webhook_agent", fake_webhook_agent)
    with TestClient(app) as client:
        response = client.post(
            "/api/runs",
            json={
                "provider": "webhook",
                "case_ids": ["case_001"],
                "webhook_url": "https://example.com/agent",
                "webhook_headers": {"Authorization": "Bearer abc"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "webhook"
    assert body["model"] == "byo-agent-webhook"
    assert seen["url"] == "https://example.com/agent"
    assert seen["headers"] == {"Authorization": "Bearer abc"}
    assert seen["case_id"] == "case_001"
    assert body["results"][0]["cost_usd"] == 0.0021


def test_webhook_agent_parses_response_via_stubbed_http(monkeypatch) -> None:
    import io
    import json as _json
    from types import SimpleNamespace
    import backend.app.agents as agents_module

    case = SimpleNamespace(
        id="case_test",
        input="Should the invoice be approved?",
        expected_answer="Approve the invoice with note.",
        expected_action="approve_invoice",
        document=SimpleNamespace(id="doc_test", name="Invoice", category="finance"),
    )
    document_text = "Invoice INV-001 total $500 approved by manager."

    captured = {}

    class FakeResponse:
        def __init__(self, payload: bytes):
            self._buffer = io.BytesIO(payload)

        def read(self, size: int = -1) -> bytes:
            return self._buffer.read(size)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = _json.loads(request.data.decode("utf-8"))
        response_payload = {
            "answer": case.expected_answer,
            "action": case.expected_action,
            "action_input": "covered",
            "retrieved_chunks": ["chunk-from-webhook"],
            "cost_usd": 0.0007,
        }
        return FakeResponse(_json.dumps(response_payload).encode("utf-8"))

    monkeypatch.setattr(agents_module.urllib.request, "urlopen", fake_urlopen)
    output = agents_module.run_webhook_agent(
        case,
        document_text,
        "https://agent.example.com/run",
        {"Authorization": "Bearer xyz"},
    )

    assert output.answer == case.expected_answer
    assert output.action == case.expected_action
    assert output.retrieved_chunks == ["chunk-from-webhook"]
    assert output.cost_usd == 0.0007
    assert captured["url"] == "https://agent.example.com/run"
    assert captured["body"]["case_id"] == case.id
    assert captured["body"]["question"] == case.input
    assert any(key.lower() == "authorization" for key in captured["headers"])


def test_upload_cases_endpoint_adds_user_golden_set() -> None:
    payload = {
        "documents": [
            {
                "id": "user_doc_1",
                "name": "user_invoice.txt",
                "category": "invoice",
                "text": "Invoice INV-9000 from Acme Co. Total $1,200. PO present. Approve.",
            }
        ],
        "cases": [
            {
                "id": "user_case_1",
                "document_id": "user_doc_1",
                "input": "Should this invoice be approved?",
                "expected_answer": "Approve invoice INV-9000.",
                "expected_facts": [
                    {"text": "INV-9000", "required": True},
                    {"text": "Acme Co", "required": False},
                ],
                "expected_action": "approve_invoice",
                "acceptable_actions": ["approve_invoice", "request_more_info"],
            }
        ],
    }
    with TestClient(app) as client:
        upload = client.post("/api/cases", json=payload)
        cases = client.get("/api/cases").json()

    assert upload.status_code == 200
    body = upload.json()
    assert body["documents_written"] == 1
    assert body["cases_written"] == 1
    assert body["replaced"] is False
    ids = {case["id"] for case in cases}
    assert "user_case_1" in ids


def test_upload_cases_rejects_unknown_document_reference() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/cases",
            json={
                "documents": [],
                "cases": [
                    {
                        "id": "orphan_case",
                        "document_id": "missing_doc",
                        "input": "x",
                        "expected_answer": "y",
                        "expected_facts": ["z"],
                        "expected_action": "noop",
                    }
                ],
            },
        )

    assert response.status_code == 400
    assert "missing_doc" in response.json()["detail"]


def test_upload_cases_requires_at_least_one_case() -> None:
    with TestClient(app) as client:
        response = client.post("/api/cases", json={"documents": [], "cases": []})

    assert response.status_code == 400


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
