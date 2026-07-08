"""Structured logging helper for guardrail decisions.

Emits a single-line, grep-friendly event: ``guardrail=<stage> action=<...>
reason=<...> key=value ...``. Used by pipelines so guardrail block/sanitize
decisions are easy to find and alert on in log aggregation.
"""

import logging


def log_guardrail_event(
    logger: logging.Logger,
    *,
    stage: str,
    action: str,
    reason: str | None = None,
    level: int = logging.INFO,
    **extra: object,
) -> None:
    """Log a structured guardrail decision.

    Example: ``log_guardrail_event(logger, stage="input", action="block",
    reason="prompt injection detected", query=query[:80])``
    """
    parts = [f"guardrail={stage}", f"action={action}"]
    if reason:
        parts.append(f"reason={reason!r}")
    for key, value in extra.items():
        parts.append(f"{key}={value!r}")
    logger.log(level, " ".join(parts))
