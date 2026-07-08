"""Unit tests for ES startup retry behavior."""

import sys
import types

import pytest


class _FakeIndices:
    def __init__(self):
        self.created = False

    def exists(self, index):
        return False

    def create(self, index, settings, mappings):
        self.created = True


class _FakeESClient:
    """Fake elasticsearch.Elasticsearch: fails ping until ``ready_after`` tries."""

    _attempts = 0
    ready_after = 0

    def __init__(self, *args, **kwargs):
        self.indices = _FakeIndices()

    def ping(self):
        type(self)._attempts += 1
        return type(self)._attempts > type(self).ready_after


@pytest.fixture
def fake_elasticsearch(monkeypatch):
    """Inject a fake ``elasticsearch`` module so setup() needs no real cluster."""
    _FakeESClient._attempts = 0
    module = types.ModuleType("elasticsearch")
    module.Elasticsearch = _FakeESClient
    monkeypatch.setitem(sys.modules, "elasticsearch", module)
    return _FakeESClient


class TestESKeywordSearchSetupRetry:
    def test_setup_waits_for_cluster(self, fake_elasticsearch):
        fake_elasticsearch.ready_after = 2  # unreachable for the first 2 pings

        from src.retrieval.es_keyword_search import ESKeywordSearch

        es = ESKeywordSearch(url="http://elasticsearch:9200")
        es.setup(base_delay=0.0)  # base_delay=0 -> retries with no real delay

        assert es.client is not None
        assert es.client.indices.created is True

    def test_setup_raises_after_exhausting_attempts(self, fake_elasticsearch):
        fake_elasticsearch.ready_after = 999  # never reachable

        from src.retrieval.es_keyword_search import ESKeywordSearch

        es = ESKeywordSearch(url="http://elasticsearch:9200")
        with pytest.raises(ConnectionError, match="not reachable"):
            es.setup(max_attempts=3, base_delay=0.0)
