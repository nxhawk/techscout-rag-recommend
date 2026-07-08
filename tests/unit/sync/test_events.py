"""Unit tests for Debezium event parsing and change detection."""

import json

from src.sync.events import (
    content_hash,
    metadata_fields,
    parse_debezium_message,
    text_changed,
)


def _payload(op, before=None, after=None) -> str:
    return json.dumps({"payload": {"op": op, "before": before, "after": after}})


ROW = {
    "product_id": "p1",
    "name": "Test Phone",
    "brand": "TestBrand",
    "category": "smartphone",
    "price": 10_000_000,
    "avg_rating": 4.2,
    "review_count": 100,
    "description": "A test phone.",
    "specifications": '{"ram": "8 GB"}',
    "pros": '["Good battery"]',
    "cons": "[]",
    "review_summary": "",
    "tags": "[]",
}


class TestParseDebeziumMessage:
    def test_parses_create(self):
        event = parse_debezium_message(_payload("c", after=ROW))
        assert event is not None
        assert event.op == "c"
        assert event.product_id == "p1"
        # JSONB columns arrive as JSON strings and must be decoded.
        assert event.after["specifications"] == {"ram": "8 GB"}
        assert event.after["pros"] == ["Good battery"]

    def test_parses_update_with_before_image(self):
        after = {**ROW, "price": 9_000_000}
        event = parse_debezium_message(_payload("u", before=ROW, after=after))
        assert event.op == "u"
        assert event.before["price"] == 10_000_000
        assert event.after["price"] == 9_000_000

    def test_parses_delete(self):
        event = parse_debezium_message(_payload("d", before=ROW))
        assert event.op == "d"
        assert event.product_id == "p1"
        assert event.after is None

    def test_parses_snapshot_read(self):
        event = parse_debezium_message(_payload("r", after=ROW))
        assert event.op == "r"

    def test_accepts_bytes(self):
        event = parse_debezium_message(_payload("c", after=ROW).encode("utf-8"))
        assert event is not None

    def test_tombstone_returns_none(self):
        assert parse_debezium_message(None) is None

    def test_garbage_returns_none(self):
        assert parse_debezium_message("not json") is None
        assert parse_debezium_message("[1, 2]") is None

    def test_unknown_op_returns_none(self):
        assert parse_debezium_message(_payload("x", after=ROW)) is None

    def test_missing_product_id_returns_none(self):
        row = {k: v for k, v in ROW.items() if k != "product_id"}
        assert parse_debezium_message(_payload("c", after=row)) is None


class TestChangeDetection:
    def test_price_only_change_is_not_text_change(self):
        before = dict(ROW)
        after = {**ROW, "price": 8_000_000, "avg_rating": 4.5, "review_count": 150}
        assert text_changed(before, after) is False
        assert content_hash(before) == content_hash(after)

    def test_description_change_is_text_change(self):
        after = {**ROW, "description": "Updated description."}
        assert text_changed(ROW, after) is True
        assert content_hash(ROW) != content_hash(after)

    def test_missing_before_image_counts_as_changed(self):
        assert text_changed(None, ROW) is True

    def test_metadata_fields_extraction(self):
        fields = metadata_fields({**ROW, "price": 123})
        assert fields == {"price": 123, "avg_rating": 4.2, "review_count": 100}
