"""Unit tests for the Prometheus /metrics endpoint and RAG-specific collectors."""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.deps import get_cached_recommend_pipeline


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_metrics_endpoint_exposes_prometheus_text(client):
    """GET /metrics returns Prometheus text with the default HTTP collectors."""
    # Generate at least one request so the HTTP metrics have a sample.
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    body = response.text
    # Default instrumentation from prometheus-fastapi-instrumentator.
    assert "http_request_duration_seconds" in body
    assert "http_requests_total" in body


def test_metrics_not_in_openapi_schema(client):
    """/metrics is excluded from the API docs (include_in_schema=False)."""
    schema = client.get("/openapi.json").json()
    assert "/metrics" not in schema["paths"]


def test_recommend_failure_increments_domain_metrics(client):
    """A pipeline error records both the error counter and pipeline timing."""

    class FailingPipeline:
        def run(self, query: str, top_k: int = 5) -> dict:
            raise RuntimeError("vector db down")

    app.dependency_overrides[get_cached_recommend_pipeline] = FailingPipeline

    resp = client.post("/api/recommend", json={"query": "camera phone", "top_k": 3})
    assert resp.status_code == 503

    body = client.get("/metrics").text
    # Recommend failures are counted, split by reason (here: generic "error").
    assert 'rag_recommend_errors_total{reason="error"}' in body
    # The pipeline-timing histogram records even when the pipeline raises.
    assert 'rag_pipeline_duration_seconds_count{pipeline="recommend"}' in body
