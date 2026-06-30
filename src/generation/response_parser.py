"""
Response Parser - Parse structured output từ LLM.
"""
import json
import re


class ResponseParser:
    """Parse and validate LLM responses."""

    def parse_json(self, response: str) -> dict | None:
        """Extract JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        # Try extracting from markdown code block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def parse_recommendation(self, response: str) -> dict:
        """Parse a recommendation response into structured format."""
        parsed = self.parse_json(response)
        if parsed:
            return parsed
        # Fallback: return raw text
        return {"text": response, "structured": False}

    def parse_comparison(self, response: str) -> dict:
        """Parse a comparison response into structured format."""
        parsed = self.parse_json(response)
        if parsed:
            return parsed
        return {"text": response, "structured": False}
