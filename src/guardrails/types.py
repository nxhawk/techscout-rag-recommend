"""Guardrail contract - shared result/action types.

Every guardrail in this package (input, context, output) returns a
``GuardrailResult`` with the same three-state contract:

- ``allow``: input/output is fine as-is.
- ``sanitize``: input/output was modified (cleaned, truncated, dropped
  fields) but is still safe to use.
- ``block``: input/output must not be used; the caller should reject the
  request (input side) or fall back to a deterministic response (output
  side).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GuardrailAction(str, Enum):
    """Outcome of a single guardrail check."""

    ALLOW = "allow"
    SANITIZE = "sanitize"
    BLOCK = "block"


@dataclass
class GuardrailResult:
    """Uniform result shape for every guardrail check in this package."""

    action: GuardrailAction
    valid: bool
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    sanitized_text: str | None = None
    sanitized_payload: dict[str, Any] | None = None

    @property
    def blocked(self) -> bool:
        return self.action == GuardrailAction.BLOCK

    @classmethod
    def allow(
        cls,
        *,
        sanitized_text: str | None = None,
        sanitized_payload: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> "GuardrailResult":
        return cls(
            action=GuardrailAction.ALLOW,
            valid=True,
            warnings=list(warnings or []),
            sanitized_text=sanitized_text,
            sanitized_payload=sanitized_payload,
        )

    @classmethod
    def sanitize(
        cls,
        *,
        sanitized_text: str | None = None,
        sanitized_payload: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
        reason: str | None = None,
    ) -> "GuardrailResult":
        return cls(
            action=GuardrailAction.SANITIZE,
            valid=True,
            reason=reason,
            warnings=list(warnings or []),
            sanitized_text=sanitized_text,
            sanitized_payload=sanitized_payload,
        )

    @classmethod
    def block(cls, reason: str, *, warnings: list[str] | None = None) -> "GuardrailResult":
        return cls(
            action=GuardrailAction.BLOCK,
            valid=False,
            reason=reason,
            warnings=list(warnings or []),
        )
