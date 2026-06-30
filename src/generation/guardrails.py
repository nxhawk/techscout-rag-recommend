"""Guardrails - Safety checks va validation cho LLM output."""
import re
import json


class Guardrails:
    """Validate and sanitize LLM inputs and outputs."""

    # Cac pattern co the gay hai hoac sai lech
    INJECTION_PATTERNS = [
        r"ignore previous instructions",
        r"ignore all previous",
        r"disregard.*instructions",
        r"you are now",
        r"new instructions:",
        r"system prompt:",
    ]

    def __init__(self, max_output_tokens: int = 4096):
        self.max_output_tokens = max_output_tokens

    def validate_input(self, query: str) -> dict:
        """Check user query for injection attempts and invalid input.

        Returns:
            dict with 'valid' bool and optional 'reason' string.
        """
        if not query or not query.strip():
            return {"valid": False, "reason": "Query trong."}

        if len(query) > 2000:
            return {"valid": False, "reason": "Query qua dai (toi da 2000 ky tu)."}

        query_lower = query.lower()
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, query_lower):
                return {"valid": False, "reason": "Query chua noi dung khong hop le."}

        return {"valid": True}

    def validate_output(self, response: str) -> dict:
        """Validate LLM response for quality and safety.

        Returns:
            dict with 'valid' bool, optional 'reason', and 'sanitized' response.
        """
        if not response or not response.strip():
            return {"valid": False, "reason": "LLM tra ve response trong."}

        sanitized = self._sanitize_output(response)

        if self._contains_hallucination_markers(sanitized):
            return {
                "valid": True,
                "warning": "Response co the chua thong tin khong chinh xac.",
                "sanitized": sanitized,
            }

        return {"valid": True, "sanitized": sanitized}

    def validate_json_output(self, response: str) -> dict:
        """Validate that LLM response contains valid JSON."""
        try:
            parsed = json.loads(response)
            return {"valid": True, "data": parsed}
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code blocks
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    return {"valid": True, "data": parsed}
                except json.JSONDecodeError:
                    pass
            return {"valid": False, "reason": "Response khong chua JSON hop le."}

    def _sanitize_output(self, text: str) -> str:
        """Remove potentially harmful content from output."""
        # Remove any script tags or HTML
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()

    def _contains_hallucination_markers(self, text: str) -> bool:
        """Detect common hallucination patterns in LLM output."""
        markers = [
            r"toi khong chac chan",
            r"co the sai",
            r"can xac minh",
            r"i'm not sure",
            r"this may be incorrect",
        ]
        text_lower = text.lower()
        return any(re.search(m, text_lower) for m in markers)
