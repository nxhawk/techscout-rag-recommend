"""
LLM Client - Gọi LLM từ nhiều provider (Anthropic, OpenAI).
"""
from typing import Optional


class LLMClient:
    """Unified LLM client supporting multiple providers."""

    def __init__(self, provider: str = "anthropic", model: str = "claude-sonnet-4-6"):
        self.provider = provider
        self.model = model
        self.client = None

    def setup(self, api_key: str) -> None:
        """Initialize LLM client."""
        if self.provider == "anthropic":
            from anthropic import Anthropic
            self.client = Anthropic(api_key=api_key)
        elif self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Generate a response from the LLM."""
        if self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text

        elif self.provider == "openai":
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return response.choices[0].message.content

        raise ValueError(f"Unsupported provider: {self.provider}")
