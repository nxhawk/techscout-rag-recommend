"""
Sync Runner - Kafka consumer loop shared by both sync workers.

At-least-once delivery: offsets are committed only after the handler applied
the event successfully. Both handlers are idempotent (deterministic chunk
ids, upsert/delete semantics), so redelivery after a crash is harmless.
"""

import logging
from typing import Any, Callable, Protocol

from src.sync.events import ChangeEvent, parse_debezium_message

logger = logging.getLogger(__name__)


class EventHandler(Protocol):
    """Anything that can apply a ChangeEvent (SearchIndexer, EmbeddingSyncer)."""

    def handle(self, event: ChangeEvent) -> str: ...


def build_consumer(bootstrap_servers: str, group_id: str, topic: str) -> Any:
    """Create and subscribe a Kafka consumer (confluent-kafka).

    Imported lazily so unit tests and API workers never need the Kafka client.
    """
    from confluent_kafka import Consumer

    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            # Read the whole topic on first start: the Debezium initial
            # snapshot is how a fresh index gets bootstrapped.
            "auto.offset.reset": "earliest",
            # Commit manually, only after the handler succeeded.
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])
    return consumer


def run_loop(
    consumer: Any,
    handler: EventHandler,
    poll_timeout: float = 1.0,
    should_stop: Callable[[], bool] | None = None,
) -> int:
    """Consume-apply-commit loop. Returns events applied (when stopped)."""
    applied = 0
    try:
        while not (should_stop and should_stop()):
            message = consumer.poll(poll_timeout)
            if message is None:
                continue
            if message.error():
                logger.error("Kafka error: %s", message.error())
                continue

            event = parse_debezium_message(message.value())
            if event is not None:
                # Let handler exceptions crash the worker: the offset is NOT
                # committed, so the event is redelivered after restart
                # (at-least-once). Swallowing errors here would silently drop
                # index updates.
                handler.handle(event)
                applied += 1
            consumer.commit(message)
    except KeyboardInterrupt:
        logger.info("Interrupted - shutting down")
    finally:
        consumer.close()
    return applied
