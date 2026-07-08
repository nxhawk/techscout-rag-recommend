"""Unit tests for POST /api/compare (pipeline mocked, no network)."""

from api.app import app
from api.deps import get_cached_compare_pipeline
from src.guardrails import InputGuardrailBlocked


class FakeComparePipeline:
    """Stand-in for ComparePipeline with a controllable result."""

    def __init__(self, result: dict | None = None, error: Exception | None = None):
        self.result = result or {}
        self.error = error
        self.calls: list[tuple[str | None, list[str] | None]] = []

    def run(self, query: str | None = None, product_ids: list[str] | None = None) -> dict:
        self.calls.append((query, product_ids))
        if self.error:
            raise self.error
        return self.result

def override_pipeline(fake: FakeComparePipeline) -> None:
    app.dependency_overrides[get_cached_compare_pipeline] = lambda: fake


def test_compare_returns_pipeline_result(client):
    fake = FakeComparePipeline(
        result={
            "comparison_table": {"products": ["A", "B"]},
            "analysis": {"criteria_comparison": [], "product_analysis": [], "conclusion": "Chọn A"},
            "warnings": [],
        }
    )
    override_pipeline(fake)

    response = client.post("/api/compare", json={"product_ids": ["p-1", "p-2"]})

    assert response.status_code == 200
    body = response.json()
    assert body["conclusion"] == "Chọn A"
    assert fake.calls == [(None, ["p-1", "p-2"])]


def test_compare_missing_query_and_ids_returns_422(client):
    override_pipeline(FakeComparePipeline())
    response = client.post("/api/compare", json={})
    assert response.status_code == 422


def test_compare_insufficient_products_returns_422(client):
    fake = FakeComparePipeline(
        result={
            "comparison_table": {},
            "markdown_table": "",
            "analysis": {},
            "warnings": [],
            "error": "Cần ít nhất 2 sản phẩm để so sánh.",
        }
    )
    override_pipeline(fake)

    response = client.post("/api/compare", json={"product_ids": ["p-1"]})

    assert response.status_code == 422


def test_compare_input_guardrail_blocked_returns_422(client):
    fake = FakeComparePipeline(
        error=InputGuardrailBlocked(reason="Yêu cầu chứa nội dung nghi vấn prompt injection.")
    )
    override_pipeline(fake)

    response = client.post("/api/compare", json={"query": "so sánh a và b"})

    assert response.status_code == 422


def test_compare_pipeline_error_returns_503(client):
    fake = FakeComparePipeline(error=RuntimeError("vector db down"))
    override_pipeline(fake)

    response = client.post("/api/compare", json={"query": "so sánh a và b"})

    assert response.status_code == 503
