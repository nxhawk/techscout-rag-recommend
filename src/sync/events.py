"""
CDC Events - Parse Debezium change events for the product_catalog table.

Debezium (Postgres connector, JSON converter without schemas) produces
messages shaped like::

    {"payload": {"op": "c"|"u"|"d"|"r", "before": {...}|null, "after": {...}|null, ...}}

``op`` meanings: c = insert, u = update, d = delete, r = snapshot read
(initial snapshot / connector restart). JSONB columns arrive as JSON strings
(io.debezium.data.Json) and are decoded here.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Fields whose change requires re-embedding (they appear in chunk text).
# avg_rating / review_count do appear in the review chunk text, but they
# drift constantly - re-embedding on every rating tick would burn embedding
# quota for a negligible relevance gain, so they are metadata-only.
TEXT_FIELDS = (
    "name",
    "brand",
    "category",
    "description",
    "specifications",
    "pros",
    "cons",
    "review_summary",
)

# Fields propagated by a cheap metadata-only update (no embedding call).
METADATA_FIELDS = ("price", "avg_rating", "review_count")

_JSONB_FIELDS = ("specifications", "pros", "cons", "tags")
_SUPPORTED_OPS = frozenset({"c", "u", "d", "r"})


@dataclass
class ChangeEvent:
    """A single row-level change captured from the catalog table."""

    op: str
    before: dict | None
    after: dict | None

    @property
    def product_id(self) -> str | None:
        row = self.after or self.before or {}
        return row.get("product_id")


def parse_debezium_message(raw: bytes | str | None) -> ChangeEvent | None:
    """Parse a Kafka message value into a ChangeEvent.

    Returns None for tombstones (null value), heartbeats, schema-change
    messages, or anything unparseable - callers skip those and commit.
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        message = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(message, dict):
        return None

    payload = message.get("payload", message)
    if not isinstance(payload, dict):
        return None
    op = payload.get("op")
    if op not in _SUPPORTED_OPS:
        return None

    event = ChangeEvent(
        op=op,
        before=_decode_row(payload.get("before")),
        after=_decode_row(payload.get("after")),
    )
    return event if event.product_id else None


def _decode_row(row: Any) -> dict | None:
    """Decode a Debezium row image (JSONB columns arrive as JSON strings)."""
    if not isinstance(row, dict):
        return None
    decoded = dict(row)
    for field in _JSONB_FIELDS:
        value = decoded.get(field)
        if isinstance(value, str):
            try:
                decoded[field] = json.loads(value)
            except json.JSONDecodeError:
                pass
    return decoded


def _normalized_text_view(row: dict) -> str:
    """Canonical JSON of the text-bearing fields (stable across dict order)."""
    view = {field: row.get(field) for field in TEXT_FIELDS}
    return json.dumps(view, ensure_ascii=False, sort_keys=True, default=str)


def content_hash(row: dict) -> str:
    """Hash of the text-bearing fields - changes iff re-embedding is needed."""
    normalized = _normalized_text_view(row)
    # Non-security fingerprint for change detection only.
    return hashlib.md5(normalized.encode("utf-8"), usedforsecurity=False).hexdigest()


def text_changed(before: dict | None, after: dict | None) -> bool:
    """True when any text-bearing field differs between the two row images."""
    if before is None or after is None:
        return True
    return _normalized_text_view(before) != _normalized_text_view(after)


def metadata_fields(row: dict) -> dict:
    """Extract the metadata-only fields for a cheap (no-embed) update."""
    fields: dict[str, Any] = {}
    for field in METADATA_FIELDS:
        if field in row and row[field] is not None:
            fields[field] = row[field]
    return fields
