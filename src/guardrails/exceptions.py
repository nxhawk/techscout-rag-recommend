"""Exceptions raised by guardrails.

Pipelines raise ``InputGuardrailBlocked`` when a request must be rejected
outright; API routes catch it and map it to an HTTP 4xx with a Vietnamese
user-facing message. Output-side failures never raise - they trigger a
deterministic fallback instead (see ``src/guardrails/fallback.py``) so the
API always returns a schema-valid response.
"""


class InputGuardrailBlocked(Exception):
    """Raised when an input guardrail's action is BLOCK."""

    def __init__(self, reason: str, warnings: list[str] | None = None):
        self.reason = reason
        self.warnings = warnings or []
        super().__init__(reason)
