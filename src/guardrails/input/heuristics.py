"""Heuristic risk checks: blank/length, URL flooding, code blocks, repeats."""

import re

from src.guardrails.base import BaseGuardrail
from src.guardrails.config import GuardrailConfig
from src.guardrails.types import GuardrailResult

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```")


def _repeated_char_pattern(threshold: int) -> re.Pattern[str]:
    return re.compile(r"(.)\1{" + str(max(threshold - 1, 1)) + r",}")


class HeuristicGuardrail(BaseGuardrail):
    """Low-risk issues -> sanitize; high-risk issues -> block."""

    name = "heuristic"

    def __init__(self, config: GuardrailConfig | None = None):
        self.config = config or GuardrailConfig()
        self._repeated_re = _repeated_char_pattern(self.config.repeated_char_threshold)

    def check(self, text: str) -> GuardrailResult:
        cfg = self.config
        stripped = (text or "").strip()

        if not stripped:
            return GuardrailResult.block(reason="Noi dung trong.")
        if len(stripped) < cfg.min_query_length:
            return GuardrailResult.block(reason="Noi dung qua ngan.")
        if len(stripped) > cfg.max_query_length:
            return GuardrailResult.block(
                reason=f"Noi dung qua dai (toi da {cfg.max_query_length} ky tu)."
            )

        urls = _URL_RE.findall(stripped)
        if len(urls) > cfg.max_url_count:
            return GuardrailResult.block(reason="Noi dung chua qua nhieu duong dan (URL).")

        if len(_CODE_FENCE_RE.findall(stripped)) > cfg.max_code_block_markers:
            return GuardrailResult.block(reason="Noi dung chua khoi code khong hop le.")

        warnings: list[str] = []
        sanitized = stripped
        if self._repeated_re.search(stripped):
            collapse_to = cfg.repeated_char_collapse_to
            sanitized = self._repeated_re.sub(lambda m: m.group(1) * collapse_to, stripped)
            warnings.append("Da rut gon ky tu lap lai bat thuong.")

        return GuardrailResult.sanitize(sanitized_text=sanitized, warnings=warnings)
