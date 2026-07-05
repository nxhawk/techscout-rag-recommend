"""Sync - CDC consumers keeping search indexes in sync with the catalog.

Debezium captures row changes on ``product_catalog`` (source of truth) into
Kafka; the workers here consume that single ordered stream and update the
two derived indexes:

- :class:`SearchIndexer` -> Elasticsearch (keyword/BM25 index)
- :class:`EmbeddingSyncer` -> Postgres + pgvector (semantic index)
"""
