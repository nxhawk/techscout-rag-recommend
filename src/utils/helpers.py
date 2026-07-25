"""Helpers - Các hàm tiện ích chung."""

import json
import logging
import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar


def load_json(filepath: str) -> Any:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, filepath: str) -> None:
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_price(price: int, currency: str = "VND") -> str:
    return f"{price:,} {currency}"


def parse_price_text(text: str) -> int:
    """Extract an integer price (VND) using only the FIRST number in the text.

    Product pages often place several numbers together (current price, the
    struck-through original price, an installment figure). Concatenating every
    digit yields an absurd value, so we take the first price-like number only.
    Handles '.' and ',' thousands separators (e.g. '29.990.000₫').
    """
    if not text:
        return 0
    # Thousands-grouped number first: 29.990.000 / 29,990,000.
    grouped = re.search(r"\d{1,3}(?:[.,]\d{3})+", text)
    if grouped:
        return int(re.sub(r"\D", "", grouped.group()))
    # Fallback: first plain run of digits.
    plain = re.search(r"\d+", text)
    return int(plain.group()) if plain else 0


# Ordered brand / product-line aliases -> canonical manufacturer brand.
# Product lines (iPhone, Galaxy, Redmi, POCO, MacBook, ...) map to their maker so
# brand-based filtering works regardless of how a listing titles the product.
_BRAND_ALIASES: tuple[tuple[str, str], ...] = (
    ("iphone", "Apple"),
    ("ipad", "Apple"),
    ("macbook", "Apple"),
    ("imac", "Apple"),
    ("airpods", "Apple"),
    ("apple", "Apple"),
    ("galaxy", "Samsung"),
    ("samsung", "Samsung"),
    ("redmi", "Xiaomi"),
    ("poco", "Xiaomi"),
    ("xiaomi", "Xiaomi"),
    ("oppo", "OPPO"),
    ("vivo", "Vivo"),
    ("realme", "Realme"),
    ("honor", "Honor"),
    ("huawei", "Huawei"),
    ("nubia", "Nubia"),
    ("itel", "Itel"),
    ("tecno", "Tecno"),
    ("infinix", "Infinix"),
    ("masstel", "Masstel"),
    ("nokia", "Nokia"),
    ("pixel", "Google"),
    ("google", "Google"),
    ("surface", "Microsoft"),
    ("microsoft", "Microsoft"),
    ("asus", "Asus"),
    ("acer", "Acer"),
    ("dell", "Dell"),
    ("lenovo", "Lenovo"),
    ("msi", "MSI"),
    ("gigabyte", "Gigabyte"),
    ("hp", "HP"),
    ("lg", "LG"),
    ("sony", "Sony"),
)


def detect_brand(name: str, default: str = "") -> str:
    """Infer the manufacturer brand from a product title.

    Matches known brand / product-line names as whole words (case-insensitive)
    and maps product lines to their maker (iPhone/MacBook -> Apple,
    Redmi/POCO -> Xiaomi). Returns ``default`` when nothing matches.
    """
    if not name:
        return default
    lowered = name.lower()
    for alias, canonical in _BRAND_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            return canonical
    return default


# -- API key rotation --------------------------------------------------------


def resolve_api_keys(env_var: str) -> list[str]:
    """Collect one or more API keys for ``env_var`` (enables token rotation).

    Reads keys from, in order:
      * ``<env_var>`` - a single key, or several separated by commas/whitespace
      * ``<env_var>_1``, ``<env_var>_2``, ... - numbered variants (stop at gap)

    Duplicates are removed while order is preserved. Example ``.env``::

        GEMINI_API_KEY=key_a,key_b
        GEMINI_API_KEY_3=key_c
    """
    raw: list[str] = list(re.split(r"[,\s]+", os.getenv(env_var, "")))
    i = 1
    while True:
        value = os.getenv(f"{env_var}_{i}")
        if value is None:
            break
        raw.append(value)
        i += 1
    keys: list[str] = []
    seen: set[str] = set()
    for key in raw:
        key = key.strip()
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def as_key_list(api_key: str | list[str]) -> list[str]:
    """Normalize a key argument (str or list) into a non-empty list of keys.

    A single string may itself contain several keys separated by commas or
    whitespace. Always returns at least ``[""]`` so callers can index [0].
    """
    if isinstance(api_key, str):
        keys = [k.strip() for k in re.split(r"[,\s]+", api_key) if k.strip()]
    else:
        keys = [k.strip() for k in api_key if isinstance(k, str) and k.strip()]
    return keys or [""]


# -- Rate-limit / retry helpers (shared by LLM + embedding clients) ----------

_RATE_LIMIT_MARKERS = (
    "resource_exhausted",
    "rate limit",
    "quota",
    "429",
    "too many requests",
)


def is_rate_limit_error(exc: Exception) -> bool:
    """True when an exception looks like a provider rate-limit / quota error."""
    return any(marker in str(exc).lower() for marker in _RATE_LIMIT_MARKERS)


def retry_delay_seconds(exc: Exception, default: float = 60.0) -> float:
    """Suggested wait (seconds) parsed from a rate-limit error, else ``default``.

    Providers advertise the wait as ``Please retry in 49.9s`` or
    ``retryDelay: '49s'``; a 1s buffer is added so the quota window fully resets.
    """
    text = str(exc)
    match = re.search(r"retry in ([\d.]+)\s*s", text, re.IGNORECASE)
    if not match:
        match = re.search(r"retrydelay['\"]?:\s*['\"]?(\d+)\s*s", text, re.IGNORECASE)
    if match:
        return float(match.group(1)) + 1.0
    return default


# -- Startup dependency wait (shared by DB / ES clients) ---------------------

_T = TypeVar("_T")


def retry_with_backoff(
    func: Callable[[], _T],
    *,
    retry_on: tuple[type[Exception], ...],
    max_attempts: int = 30,
    base_delay: float = 1.0,
    max_delay: float = 5.0,
    logger: logging.Logger | None = None,
    description: str = "operation",
    sleep: Callable[[float], None] = time.sleep,
) -> _T:
    """Call ``func`` and retry on ``retry_on`` with exponential backoff.

    Lets a worker wait for a slow dependency (Postgres, Elasticsearch) to come
    up at startup instead of crashing on the first connection refusal. Waits
    ``min(base_delay * 2**(n-1), max_delay)`` seconds between attempts and
    re-raises the last exception once ``max_attempts`` is exhausted. ``sleep`` is
    injectable so tests run without real delays.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except retry_on as exc:
            if attempt >= max_attempts:
                raise
            delay = min(base_delay * 2 ** (attempt - 1), max_delay)
            if logger is not None:
                logger.warning(
                    "%s not ready (attempt %d/%d): %s - retrying in %.1fs",
                    description,
                    attempt,
                    max_attempts,
                    exc,
                    delay,
                )
            sleep(delay)
    # The loop always returns or raises; this satisfies type checkers.
    raise AssertionError("retry_with_backoff exhausted without raising")  # pragma: no cover
