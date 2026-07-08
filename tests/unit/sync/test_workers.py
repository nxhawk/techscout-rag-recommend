"""Unit tests for the CDC sync workers (fakes only - no Kafka/ES/DB)."""

import pytest

from src.sync.events import ChangeEvent, content_hash
from src.sync.embedding_worker import EmbeddingSyncer
from src.sync.indexer_worker import SearchIndexer


class FakeES:
    """Minimal stand-in for ESKeywordSearch."""

    def __init__(self):
        self.docs: dict[str, dict] = {}

    def upsert_chunks(self, ids, documents, metadatas):
        for chunk_id, document, metadata in zip(ids, documents, metadatas):
            self.docs[chunk_id] = {"document": document, **metadata}
        return len(ids)

    def delete_product(self, product_id):
        stale = [k for k, v in self.docs.items() if v.get("product_id") == product_id]
        for key in stale:
            del self.docs[key]
        return len(stale)


class FakeVectorStore:
    """Minimal stand-in for VectorStore (per-product operations)."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def add_documents(self, ids, embeddings, documents, metadatas):
        for chunk_id, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self.rows[chunk_id] = {"embedding": emb, "document": doc, "metadata": meta}

    def delete_product(self, product_id):
        stale = [k for k, v in self.rows.items() if v["metadata"].get("product_id") == product_id]
        for key in stale:
            del self.rows[key]
        return len(stale)

    def update_product_metadata(self, product_id, fields):
        count = 0
        for row in self.rows.values():
            if row["metadata"].get("product_id") == product_id:
                row["metadata"].update(fields)
                count += 1
        return count

    def get_product_content_hash(self, product_id):
        for row in self.rows.values():
            if row["metadata"].get("product_id") == product_id:
                return row["metadata"].get("content_hash")
        return None


class FakeEmbedder:
    def __init__(self):
        self.calls = 0

    def embed_batch(self, texts):
        self.calls += 1
        return [[0.1, 0.2] for _ in texts]


@pytest.fixture
def product_row(sample_product):
    return dict(sample_product)


@pytest.fixture
def fake_es():
    return FakeES()


@pytest.fixture
def fake_store():
    return FakeVectorStore()


@pytest.fixture
def fake_embedder():
    return FakeEmbedder()


class TestSearchIndexer:
    def test_create_indexes_chunks(self, fake_es, product_row):
        indexer = SearchIndexer(fake_es)
        action = indexer.handle(ChangeEvent(op="c", before=None, after=product_row))
        assert action == "upserted"
        assert "test-001_description" in fake_es.docs
        assert all(v["product_id"] == "test-001" for v in fake_es.docs.values())

    def test_update_drops_stale_chunk_types(self, fake_es, product_row):
        indexer = SearchIndexer(fake_es)
        indexer.handle(ChangeEvent(op="c", before=None, after=product_row))
        assert "test-001_review" in fake_es.docs  # has review_summary

        # Remove the review summary -> review chunk must disappear.
        updated = {**product_row, "review_summary": ""}
        indexer.handle(ChangeEvent(op="u", before=product_row, after=updated))
        assert "test-001_review" not in fake_es.docs
        assert "test-001_description" in fake_es.docs

    def test_delete_removes_all_chunks(self, fake_es, product_row):
        indexer = SearchIndexer(fake_es)
        indexer.handle(ChangeEvent(op="c", before=None, after=product_row))
        action = indexer.handle(ChangeEvent(op="d", before=product_row, after=None))
        assert action == "deleted"
        assert fake_es.docs == {}

    def test_replay_is_idempotent(self, fake_es, product_row):
        indexer = SearchIndexer(fake_es)
        event = ChangeEvent(op="r", before=None, after=product_row)
        indexer.handle(event)
        snapshot = dict(fake_es.docs)
        indexer.handle(event)  # redelivery
        assert fake_es.docs == snapshot


class TestEmbeddingSyncer:
    def _syncer(self, fake_embedder, fake_store):
        return EmbeddingSyncer(fake_embedder, fake_store)

    def test_create_embeds_chunks(self, fake_embedder, fake_store, product_row):
        syncer = self._syncer(fake_embedder, fake_store)
        action = syncer.handle(ChangeEvent(op="c", before=None, after=product_row))
        assert action == "embedded"
        assert fake_embedder.calls == 1
        assert "test-001_description" in fake_store.rows

    def test_price_only_update_skips_embedding(self, fake_embedder, fake_store, product_row):
        syncer = self._syncer(fake_embedder, fake_store)
        syncer.handle(ChangeEvent(op="c", before=None, after=product_row))

        updated = {**product_row, "price": 8_888_888, "avg_rating": 4.9}
        action = syncer.handle(ChangeEvent(op="u", before=product_row, after=updated))
        assert action == "metadata"
        assert fake_embedder.calls == 1  # no second embedding call
        meta = fake_store.rows["test-001_description"]["metadata"]
        assert meta["price"] == 8_888_888
        assert meta["avg_rating"] == 4.9

    def test_text_update_reembeds(self, fake_embedder, fake_store, product_row):
        syncer = self._syncer(fake_embedder, fake_store)
        syncer.handle(ChangeEvent(op="c", before=None, after=product_row))

        updated = {**product_row, "description": "Hoàn toàn mới."}
        action = syncer.handle(ChangeEvent(op="u", before=product_row, after=updated))
        assert action == "embedded"
        assert fake_embedder.calls == 2
        stored_hash = fake_store.rows["test-001_description"]["metadata"]["content_hash"]
        assert stored_hash == content_hash(updated)

    def test_snapshot_replay_skips_embedding(self, fake_embedder, fake_store, product_row):
        """Debezium initial-snapshot replay must cost zero embedding calls."""
        syncer = self._syncer(fake_embedder, fake_store)
        syncer.handle(ChangeEvent(op="c", before=None, after=product_row))
        action = syncer.handle(ChangeEvent(op="r", before=None, after=product_row))
        assert action == "metadata"
        assert fake_embedder.calls == 1

    def test_update_without_before_image_uses_hash(self, fake_embedder, fake_store, product_row):
        syncer = self._syncer(fake_embedder, fake_store)
        syncer.handle(ChangeEvent(op="c", before=None, after=product_row))
        # No before image (e.g. REPLICA IDENTITY not FULL) but same content:
        action = syncer.handle(ChangeEvent(op="u", before=None, after=product_row))
        assert action == "metadata"
        assert fake_embedder.calls == 1

    def test_delete_removes_vectors(self, fake_embedder, fake_store, product_row):
        syncer = self._syncer(fake_embedder, fake_store)
        syncer.handle(ChangeEvent(op="c", before=None, after=product_row))
        action = syncer.handle(ChangeEvent(op="d", before=product_row, after=None))
        assert action == "deleted"
        assert fake_store.rows == {}
