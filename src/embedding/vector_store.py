"""
Vector Store - Manage connection and operations with the vector database.
Backend: PostgreSQL + pgvector (cosine similarity).
"""
import json
import os
import re
from typing import Any, Optional

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5432/rag_products"


class VectorStore:
    """Manage vector database operations backed by Postgres + pgvector."""

    def __init__(
        self,
        provider: str = "pgvector",
        collection_name: str = "products",
        embedding_dim: int = 1536,
    ):
        self.provider = provider
        self.collection_name = collection_name
        self.embedding_dim = embedding_dim
        self.conn = None
        # Sanitize collection name to a safe SQL identifier
        self.table_name = re.sub(r"[^a-zA-Z0-9_]", "_", collection_name)

    def setup(self, **kwargs) -> None:
        """Initialize the Postgres connection, extension, table and index.

        Connection string resolution order:
        1. ``dsn`` keyword argument
        2. ``DATABASE_URL`` environment variable
        3. Local default (``localhost:5432/rag_products``)

        ``connect_timeout`` (seconds, default 5) caps how long the initial
        connection may take, so an unreachable database fails fast instead of
        hanging for the OS-level TCP timeout (minutes on some systems).
        """
        import psycopg
        from pgvector.psycopg import register_vector

        dsn = kwargs.get("dsn") or os.getenv("DATABASE_URL", DEFAULT_DSN)
        connect_timeout = kwargs.get("connect_timeout", 5)
        self.conn = psycopg.connect(dsn, autocommit=True, connect_timeout=connect_timeout)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id TEXT PRIMARY KEY,
                document TEXT NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                embedding vector({self.embedding_dim}) NOT NULL
            )
            """
        )
        self.conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx
            ON {self.table_name}
            USING hnsw (embedding vector_cosine_ops)
            """
        )

    def add_documents(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Upsert documents with embeddings into the store."""
        with self.conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {self.table_name} (id, document, metadata, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    document = EXCLUDED.document,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding
                """,
                [
                    (doc_id, doc, json.dumps(meta, ensure_ascii=False), str(emb))
                    for doc_id, doc, meta, emb in zip(
                        ids, documents, metadatas, embeddings
                    )
                ],
            )

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: Optional[dict] = None,
    ) -> dict:
        """Query similar documents by cosine distance.

        Returns a dict shaped like ``{"ids": [[...]], "documents": [[...]],
        "metadatas": [[...]], "distances": [[...]]}`` (one nested list per
        query) so downstream consumers can iterate results uniformly.
        """
        where_sql, params = self._build_where_sql(where)
        sql = f"""
            SELECT id, document, metadata,
                   embedding <=> %s::vector AS distance
            FROM {self.table_name}
            {where_sql}
            ORDER BY distance ASC
            LIMIT %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, [str(query_embedding), *params, n_results])
            rows = cur.fetchall()

        return {
            "ids": [[row[0] for row in rows]],
            "documents": [[row[1] for row in rows]],
            "metadatas": [[row[2] for row in rows]],
            "distances": [[float(row[3]) for row in rows]],
        }

    def list_documents(self, limit: int | None = None) -> dict:
        """Return all ids/documents/metadatas (no embeddings).

        Used to build in-memory keyword indexes (BM25) at startup. Shaped like
        ``{"ids": [...], "documents": [...], "metadatas": [...]}`` (flat lists,
        single snapshot - not the nested per-query shape of ``query``).
        """
        sql = f"SELECT id, document, metadata FROM {self.table_name} ORDER BY id"
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return {
            "ids": [row[0] for row in rows],
            "documents": [row[1] for row in rows],
            "metadatas": [row[2] for row in rows],
        }

    def delete_product(self, product_id: str) -> int:
        """Delete all chunks belonging to a product. Returns rows deleted."""
        with self.conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self.table_name} WHERE metadata->>'product_id' = %s",
                (product_id,),
            )
            return cur.rowcount

    def update_product_metadata(self, product_id: str, fields: dict) -> int:
        """Merge ``fields`` into the metadata of every chunk of a product.

        Used by the embedding sync worker for metadata-only changes (price,
        rating) so embeddings are not recomputed. Returns rows updated.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {self.table_name}
                SET metadata = metadata || %s::jsonb
                WHERE metadata->>'product_id' = %s
                """,
                (json.dumps(fields, ensure_ascii=False), product_id),
            )
            return cur.rowcount

    def get_product_content_hash(self, product_id: str) -> str | None:
        """Return the stored content hash for a product (or None).

        The embedding sync worker stores a hash of the text-bearing fields in
        chunk metadata; comparing it lets snapshot replays skip re-embedding.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT metadata->>'content_hash' FROM {self.table_name}
                WHERE metadata->>'product_id' = %s LIMIT 1
                """,
                (product_id,),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def delete_collection(self) -> None:
        """Drop the table backing the current collection."""
        self.conn.execute(f"DROP TABLE IF EXISTS {self.table_name}")

    def close(self) -> None:
        """Close the database connection."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    # Whitelisted comparison operators for numeric metadata filters.
    _OPERATORS = {"$eq": "=", "$lt": "<", "$lte": "<=", "$gt": ">", "$gte": ">="}

    def _build_where_sql(self, where: Optional[dict]) -> tuple[str, list[Any]]:
        """Translate a metadata filter dict into a SQL WHERE clause.

        Supports simple equality filters (``{"brand": "Apple"}``), numeric
        range filters (``{"price": {"$lte": 15000000}}`` with ``$eq``/``$lt``/
        ``$lte``/``$gt``/``$gte``) and ``{"$and": [{...}, {...}]}`` composites
        over JSONB metadata. All keys and values are passed as bound
        parameters; operators come from a fixed whitelist.
        """
        if not where:
            return "", []

        conditions = where.get("$and", [where]) if isinstance(where, dict) else []
        clauses: list[str] = []
        params: list[Any] = []
        for condition in conditions:
            for key, value in condition.items():
                if isinstance(value, dict):
                    for op, op_value in value.items():
                        sql_op = self._OPERATORS.get(op)
                        if sql_op is None:
                            continue
                        clauses.append(f"(metadata->>%s)::numeric {sql_op} %s")
                        params.extend([key, op_value])
                else:
                    clauses.append("metadata->>%s = %s")
                    params.extend([key, str(value)])
        if not clauses:
            return "", []
        return "WHERE " + " AND ".join(clauses), params
