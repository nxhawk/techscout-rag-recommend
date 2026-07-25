"""LLM Client - Pluggable multi-provider interface for text generation.

The client delegates to a registered *provider* implementation. Supported
out of the box: Anthropic, OpenAI, Gemini.

Adding a new provider (e.g. a self-hosted or third-party model) is a two-step,
open/closed change - no edits to ``LLMClient`` are required:

    @register_llm_provider("myprovider")
    class MyProvider(BaseLLMProvider):
        api_key_env = "MYPROVIDER_API_KEY"

        def setup(self, api_key: str) -> None:
            self.client = ...

        def generate(self, prompt, system_prompt="", max_tokens=2048,
                     temperature=0.3) -> str:
            return ...
"""
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import ClassVar

from src.constants import DEFAULT_LLM_MODEL
from src.utils.helpers import as_key_list, is_rate_limit_error, retry_delay_seconds


class BaseLLMProvider(ABC):
    """Common interface every text-generation provider must implement."""

    #: Environment variable that holds this provider's API key.
    api_key_env: ClassVar[str] = ""

    def __init__(self, model: str):
        self.model = model
        self.client = None  # Initialized in setup()

    @abstractmethod
    def setup(self, api_key: str) -> None:
        """Initialize the underlying SDK client."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        json_output: bool = False,
    ) -> str:
        """Generate a completion for the given prompt.

        ``json_output=True`` requests strict JSON output using the provider's
        native JSON mode where available (Gemini, OpenAI); providers without
        one fall back to prompt instructions (Anthropic).
        """


# --- Provider registry -----------------------------------------------------

_LLM_PROVIDERS: dict[str, type[BaseLLMProvider]] = {}


def register_llm_provider(
    name: str,
) -> Callable[[type[BaseLLMProvider]], type[BaseLLMProvider]]:
    """Class decorator: register a provider implementation under ``name``."""

    def wrapper(cls: type[BaseLLMProvider]) -> type[BaseLLMProvider]:
        _LLM_PROVIDERS[name] = cls
        return cls

    return wrapper


def available_llm_providers() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(_LLM_PROVIDERS)


# --- Concrete providers ----------------------------------------------------

@register_llm_provider("anthropic")
class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude models via the ``anthropic`` SDK."""

    api_key_env = "ANTHROPIC_API_KEY"

    def setup(self, api_key: str) -> None:
        from anthropic import Anthropic

        self.client = Anthropic(api_key=api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        json_output: bool = False,
    ) -> str:
        # Anthropic has no dedicated JSON mode; JSON format is enforced via
        # the prompt (json_output intentionally unused here).
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text


@register_llm_provider("openai")
class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT models via the ``openai`` SDK."""

    api_key_env = "OPENAI_API_KEY"

    def setup(self, api_key: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        json_output: bool = False,
    ) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_output:
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content


@register_llm_provider("gemini")
class GeminiProvider(BaseLLMProvider):
    """Google Gemini models via the ``google-genai`` SDK."""

    api_key_env = "GEMINI_API_KEY"

    def setup(self, api_key: str) -> None:
        from google import genai

        self.client = genai.Client(api_key=api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        json_output: bool = False,
    ) -> str:
        from google.genai import types

        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        config_kwargs: dict = {
            "max_output_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_output:
            # Native JSON mode: no prose preamble/markdown fences, so the
            # response parses reliably and fits within max_output_tokens.
            config_kwargs["response_mime_type"] = "application/json"
        if "pro" not in self.model:
            # gemini-2.5-flash/flash-lite think by default, and thinking
            # tokens are drawn from the SAME max_output_tokens budget as the
            # final answer. For a structured-output task like this, letting
            # the model "think" can silently exhaust the budget before it
            # writes any JSON, producing an empty/truncated response that
            # fails the output guardrail on every call. Disable thinking so
            # the full budget goes to the actual completion. gemini-2.5-pro
            # does not support thinking_budget=0, so it is left untouched.
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config=types.GenerateContentConfig(**config_kwargs),
        )
        return response.text


# --- Facade (public, backward-compatible API) ------------------------------

class LLMClient:
    """Unified LLM client that delegates to a registered provider."""

    # provider name -> API key env var. Built from the registry so it stays
    # in sync automatically when new providers are registered above.
    PROVIDER_API_KEY_ENV: ClassVar[dict[str, str]] = {
        name: cls.api_key_env for name, cls in _LLM_PROVIDERS.items()
    }

    def __init__(
        self,
        provider: str = "anthropic",
        model: str = DEFAULT_LLM_MODEL,
        max_retries: int = 6,
    ):
        if provider not in _LLM_PROVIDERS:
            raise ValueError(
                f"Unsupported provider: {provider}. "
                f"Available: {available_llm_providers()}"
            )
        self.provider = provider
        self.model = model
        # How many times to wait-for-quota (after exhausting all keys) before
        # giving up on a request.
        self.max_retries = max_retries
        self._impl: BaseLLMProvider = _LLM_PROVIDERS[provider](model)
        self._keys: list[str] = [""]
        self._key_idx: int = 0

    def setup(self, api_key: str | list[str]) -> None:
        """Initialize the LLM client for the configured provider.

        ``api_key`` may be a single key or a list of keys (or a comma/space
        separated string). Extra keys are used for rotation on rate limits.
        """
        self._keys = as_key_list(api_key)
        self._key_idx = 0
        self._impl.setup(self._keys[0])

    def _rotate_key(self) -> bool:
        """Switch the client to the next configured key. False if only one key."""
        if len(self._keys) <= 1:
            return False
        self._key_idx = (self._key_idx + 1) % len(self._keys)
        self._impl.setup(self._keys[self._key_idx])
        return True

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.3,
        json_output: bool = False,
    ) -> str:
        """Generate a response, rotating keys then waiting on rate-limit errors.

        On a rate-limit error it first tries the remaining keys; only when they
        are all throttled does it sleep for the provider-suggested delay and
        start another round (up to ``max_retries`` waits).
        """
        waits = 0
        rotations = 0
        while True:
            try:
                return self._impl.generate(
                    prompt, system_prompt, max_tokens, temperature, json_output
                )
            except Exception as exc:
                if not is_rate_limit_error(exc):
                    raise
                if rotations < len(self._keys) - 1 and self._rotate_key():
                    rotations += 1
                    continue
                if waits >= self.max_retries:
                    raise
                time.sleep(retry_delay_seconds(exc))
                waits += 1
                rotations = 0

    @property
    def client(self):
        """Expose the underlying SDK client (backward compatibility)."""
        return self._impl.client
