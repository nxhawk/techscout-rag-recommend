"""Base guardrail interface and a chain runner for input guardrails.

To add a new input guardrail:

1. Subclass ``BaseGuardrail`` and implement ``check(text) -> GuardrailResult``.
2. Add an instance to the list built in ``src/guardrails/input/__init__.py``
   (``build_input_chain``).

The chain runs guardrails in order and short-circuits on the first
``BLOCK``. Any ``sanitized_text`` returned by a guardrail is fed into the
next one, so guardrails can be layered (e.g. normalize -> injection check ->
heuristics).
"""

from abc import ABC, abstractmethod

from src.guardrails.types import GuardrailAction, GuardrailResult


class BaseGuardrail(ABC):
    """A single input-side check. Stateless and side-effect free."""

    name: str = "base"

    @abstractmethod
    def check(self, text: str) -> GuardrailResult:
        """Evaluate ``text`` and return a GuardrailResult."""
        raise NotImplementedError


class GuardrailChain:
    """Runs a sequence of ``BaseGuardrail`` checks against the same input."""

    def __init__(self, guardrails: list[BaseGuardrail]):
        self.guardrails = guardrails

    def run(self, text: str) -> GuardrailResult:
        current_text = text
        warnings: list[str] = []
        for guardrail in self.guardrails:
            result = guardrail.check(current_text)
            warnings.extend(result.warnings)
            if result.action == GuardrailAction.BLOCK:
                return GuardrailResult.block(
                    reason=result.reason or f"Bi tu choi boi guardrail '{guardrail.name}'.",
                    warnings=warnings,
                )
            if result.sanitized_text is not None:
                current_text = result.sanitized_text
        return GuardrailResult.allow(sanitized_text=current_text, warnings=warnings)
