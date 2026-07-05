"""
Product Repository - Source-of-truth ``product_catalog`` table in Postgres.

This table is the single source of truth for product data:

- The CRUD API (``api/routes/products.py``) writes ONLY here.
- Debezium captures row changes from this table (CDC) into Kafka.
- Search indexes (Elasticsearch keyword index, pgvector embeddings) are
  DERIVED from it by the sync workers in ``src/sync/`` and must never be
  written directly by API handlers.

Table names are trusted internal identifiers; all runtime values are passed
as parameterized ``%s`` placeholders.
"""

import json
import os
import re
from typing import Any

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5432/rag_products"

# Columns in insert order. JSONB columns are serialized with json.dumps.
_COLUMNS = (
    "product_id",
    "name",
    "brand",
    "category",
    "price",
    "currency",
    "avg_rating",
    "review_count",
    "description",
    "specifications",
    "pros",
    "cons",
    "review_summary",
    "tags",
)
_JSONB_COLUMNS = frozenset({"specifications", "pros", "cons", "tags"})
_JSONB_DEFAULTS: dict[str, Any] = {
    "specifications": {},
    "pros": [],
    "cons": [],
    "tags": [],
}


class ProductRepository:
    """CRUD access to the source-of-truth product table."""

    def __init__(self, table_name: str = "product_catalog"):
        # Sanitize to a safe SQL identifier (trusted internal config only).
        self.table_name = re.sub(r"[^a-zA-Z0-9_]", "_", table_name)
        self.conn = None

    def setup(self, dsn: str | None = None, connect_timeout: int = 5) -> None:
        """Connect and create the table if missing.

        ``REPLICA IDENTITY FULL`` makes Postgres emit full before-images on
        UPDATE/DELETE, which the embedding worker needs to decide between
        re-embedding (text changed) and a metadata-only update (price/rating).
        """
        import psycopg

        dsn = dsn or os.getenv("DATABASE_URL", DEFAULT_DSN)
        self.conn = psycopg.connect(dsn, autocommit=True, connect_timeout=connect_timeout)
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                product_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                brand TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                price BIGINT NOT NULL DEFAULT 0,
                currency TEXT NOT NULL DEFAULT 'VND',
                avg_rating DOUBLE PRECISION NOT NULL DEFAULT 0,
                review_count INTEGER NOT NULL DEFAULT 0,
                description TEXT NOT NULL DEFAULT '',
                specifications JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                pros JSONB NOT NULL DEFAULT '[]'::jsonb,
                cons JSONB NOT NULL DEFAULT '[]'::jsonb,
                review_summary TEXT NOT NULL DEFAULT '',
                tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        self.conn.execute(f"ALTER TABLE {self.table_name} REPLICA IDENTITY FULL")

    # ------------------------------------------------------------------ CRUD

    def create(self, product: dict) -> bool:
        """Insert a new product. Returns False if the id already exists."""
        cols, values = self._row_values(product)
        placeholders = ", ".join(["%s"] * len(cols))
        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {self.table_name} ({", ".join(cols)})
                VALUES ({placeholders})
                ON CONFLICT (product_id) DO NOTHING
                """,
                values,
            )
            return cur.rowcount > 0

    def upsert(self, product: dict) -> None:
        """Insert or fully replace a product row."""
        cols, values = self._row_values(product)
        placeholders = ", ".join(["%s"] * len(cols))
        updates = ", ".join(f"{col} = EXCLUDED.{col}" for col in cols if col != "product_id")
        self.conn.execute(
            f"""
            INSERT INTO {self.table_name} ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT (product_id) DO UPDATE SET {updates}, updated_at = now()
            """,
            values,
        )

    def upsert_many(self, products: list[dict]) -> int:
        """Bulk upsert (used by scripts/ingest.py for bootstrap)."""
        for product in products:
            self.upsert(product)
        return len(products)

    def update(self, product_id: str, fields: dict) -> dict | None:
        """Partial update: merge ``fields`` into the existing row.

        Returns the updated product, or None if the id does not exist.
        """
        existing = self.get(product_id)
        if existing is None:
            return None
        merged = {**existing, **{k: v for k, v in fields.items() if v is not None}}
        merged["product_id"] = product_id
        self.upsert(merged)
        return self.get(product_id)

    def delete(self, product_id: str) -> bool:
        """Delete a product. Returns False if it did not exist."""
        with self.conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self.table_name} WHERE product_id = %s",
                (product_id,),
            )
            return cur.rowcount > 0

    def get(self, product_id: str) -> dict | None:
        """Fetch a single product as a dict, or None."""
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM {self.table_name} WHERE product_id = %s",
                (product_id,),
            )
            row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def list_products(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """List products ordered by id (paginated)."""
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM {self.table_name} "
                "ORDER BY product_id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count(self) -> int:
        """Total number of products."""
        with self.conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {self.table_name}")
            return int(cur.fetchone()[0])

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _row_values(product: dict) -> tuple[tuple[str, ...], list[Any]]:
        """Map a product dict onto (columns, parameter values)."""
        values: list[Any] = []
        for col in _COLUMNS:
            value = product.get(col, _JSONB_DEFAULTS.get(col))
            if col in _JSONB_COLUMNS:
                value = json.dumps(value or _JSONB_DEFAULTS[col], ensure_ascii=False)
            elif value is None:
                value = "" if col not in ("price", "avg_rating", "review_count") else 0
            values.append(value)
        return _COLUMNS, values

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        product = dict(zip(_COLUMNS, row))
        product["price"] = int(product["price"] or 0)
        product["avg_rating"] = float(product["avg_rating"] or 0)
        product["review_count"] = int(product["review_count"] or 0)
        for col in _JSONB_COLUMNS:
            # psycopg decodes jsonb to Python objects already; tolerate strings.
            if isinstance(product[col], str):
                product[col] = json.loads(product[col])
        return product
