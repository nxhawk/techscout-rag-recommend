"""
HTTP Client - Wrapper httpx có retry, rate limit và kiểm tra robots.txt.
"""
import asyncio

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.crawler.config import CrawlerConfig
from src.crawler.exceptions import FetchError, RobotsDisallowed
from src.crawler.rate_limiter import RateLimiter
from src.crawler.robots import RobotsChecker
from src.utils.logger import setup_logger

logger = setup_logger("crawler.http")

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class HttpClient:
    """Fetch HTML pages politely with retries and optional robots.txt checks.

    Usable both synchronously (`get`) and asynchronously (`aget`). Async is used
    to fetch many product detail pages concurrently.
    """

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self._headers = {
            "User-Agent": config.user_agent,
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        }
        self._rate_limiter = RateLimiter(delay=config.request_delay)
        self._robots = (
            RobotsChecker(config.user_agent) if config.respect_robots else None
        )
        self._sync_client = httpx.Client(
            headers=self._headers,
            timeout=config.timeout,
            follow_redirects=True,
        )

    def _check_robots(self, url: str) -> None:
        if self._robots and not self._robots.can_fetch(url):
            raise RobotsDisallowed(url)

    def get(self, url: str) -> str:
        """Synchronously fetch a URL and return its HTML body."""
        self._check_robots(url)
        self._rate_limiter.wait()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=self.config.retry_backoff),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        def _do() -> str:
            resp = self._sync_client.get(url)
            resp.raise_for_status()
            return resp.text

        try:
            logger.debug("GET %s", url)
            return _do()
        except httpx.HTTPStatusError as exc:
            raise FetchError(url, exc.response.status_code, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise FetchError(url, message=str(exc)) from exc

    def post_json(self, url: str, payload: dict) -> str:
        """Synchronously POST a JSON payload (e.g. a GraphQL query) to a URL.

        Applies the same politeness rules as `get` (robots, rate limit, retry).
        """
        self._check_robots(url)
        self._rate_limiter.wait()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=self.config.retry_backoff),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        def _do() -> str:
            resp = self._sync_client.post(url, json=payload)
            resp.raise_for_status()
            return resp.text

        try:
            logger.debug("POST %s", url)
            return _do()
        except httpx.HTTPStatusError as exc:
            raise FetchError(url, exc.response.status_code, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise FetchError(url, message=str(exc)) from exc

    async def aget(self, url: str, client: httpx.AsyncClient) -> str:
        """Asynchronously fetch a URL using a shared AsyncClient."""
        self._check_robots(url)
        await self._rate_limiter.await_ready()

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=self.config.retry_backoff),
            retry=retry_if_exception_type(_RETRYABLE),
        )
        async def _do() -> str:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text

        try:
            logger.debug("aGET %s", url)
            return await _do()
        except httpx.HTTPStatusError as exc:
            raise FetchError(url, exc.response.status_code, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise FetchError(url, message=str(exc)) from exc

    async def get_many(self, urls: list[str]) -> list[str | None]:
        """Fetch many URLs concurrently, bounded by config.concurrency.

        Returns HTML bodies aligned with `urls`; failed fetches yield None.
        """
        semaphore = asyncio.Semaphore(self.config.concurrency)

        async with httpx.AsyncClient(
            headers=self._headers,
            timeout=self.config.timeout,
            follow_redirects=True,
        ) as client:

            async def _bounded(u: str) -> str | None:
                async with semaphore:
                    try:
                        return await self.aget(u, client)
                    except FetchError as exc:
                        logger.warning("Skip %s: %s", u, exc)
                        return None

            return await asyncio.gather(*(_bounded(u) for u in urls))

    def close(self) -> None:
        """Close the underlying sync client."""
        self._sync_client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
