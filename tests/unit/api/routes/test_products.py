"""Unit tests for the product CRUD API (fake repository - no DB)."""

import pytest
from fastapi.testclient import TestClient

from api.app import app
from api.deps import get_cached_product_repository


class FakeRepository:
    """Dict-backed stand-in for ProductRepository."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def create(self, product):
        if product["product_id"] in self.rows:
            return False
        self.rows[product["product_id"]] = dict(product)
        return True

    def upsert(self, product):
        self.rows[product["product_id"]] = dict(product)

    def update(self, product_id, fields):
        if product_id not in self.rows:
            return None
        self.rows[product_id].update({k: v for k, v in fields.items() if v is not None})
        return dict(self.rows[product_id])

    def delete(self, product_id):
        return self.rows.pop(product_id, None) is not None

    def get(self, product_id):
        row = self.rows.get(product_id)
        return dict(row) if row else None

    def list_products(self, limit=50, offset=0):
        rows = sorted(self.rows.values(), key=lambda r: r["product_id"])
        return [dict(r) for r in rows[offset : offset + limit]]

    def count(self):
        return len(self.rows)


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture
def client(fake_repo):
    app.dependency_overrides[get_cached_product_repository] = lambda: fake_repo
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


PAYLOAD = {
    "product_id": "p-100",
    "name": "Điện thoại Test",
    "brand": "TestBrand",
    "category": "smartphone",
    "price": 9_990_000,
    "description": "Mô tả sản phẩm.",
}


class TestCreateProduct:
    def test_create_returns_201(self, client, fake_repo):
        response = client.post("/api/products", json=PAYLOAD)
        assert response.status_code == 201
        body = response.json()
        assert body["product_id"] == "p-100"
        assert "đồng bộ" in body["message"]
        assert fake_repo.rows["p-100"]["price"] == 9_990_000

    def test_duplicate_returns_409(self, client):
        client.post("/api/products", json=PAYLOAD)
        response = client.post("/api/products", json=PAYLOAD)
        assert response.status_code == 409

    def test_id_generated_from_name(self, client):
        payload = {k: v for k, v in PAYLOAD.items() if k != "product_id"}
        response = client.post("/api/products", json=payload)
        assert response.status_code == 201
        assert response.json()["product_id"].startswith("i-n-tho-i-test-")

    def test_name_required(self, client):
        response = client.post("/api/products", json={"price": 1})
        assert response.status_code == 422


class TestUpdateProduct:
    def test_partial_update(self, client, fake_repo):
        client.post("/api/products", json=PAYLOAD)
        response = client.put("/api/products/p-100", json={"price": 8_500_000})
        assert response.status_code == 200
        assert fake_repo.rows["p-100"]["price"] == 8_500_000
        assert fake_repo.rows["p-100"]["name"] == "Điện thoại Test"  # untouched

    def test_missing_product_returns_404(self, client):
        response = client.put("/api/products/nope", json={"price": 1})
        assert response.status_code == 404

    def test_empty_body_returns_422(self, client):
        client.post("/api/products", json=PAYLOAD)
        response = client.put("/api/products/p-100", json={})
        assert response.status_code == 422


class TestDeleteProduct:
    def test_delete(self, client, fake_repo):
        client.post("/api/products", json=PAYLOAD)
        response = client.delete("/api/products/p-100")
        assert response.status_code == 200
        assert fake_repo.rows == {}

    def test_missing_product_returns_404(self, client):
        response = client.delete("/api/products/nope")
        assert response.status_code == 404


class TestReadProducts:
    def test_get_product(self, client):
        client.post("/api/products", json=PAYLOAD)
        response = client.get("/api/products/p-100")
        assert response.status_code == 200
        assert response.json()["product"]["name"] == "Điện thoại Test"

    def test_list_products(self, client):
        client.post("/api/products", json=PAYLOAD)
        client.post("/api/products", json={**PAYLOAD, "product_id": "p-200"})
        response = client.get("/api/products", params={"limit": 1})
        body = response.json()
        assert response.status_code == 200
        assert body["total"] == 2
        assert len(body["products"]) == 1
