"""Client for the platform service-registry (services/service-registry).

On startup, registers {name, host, port, health} and heartbeats on an
interval; on shutdown, deregisters. If REGISTRY_URL is not set, registration
is skipped entirely (e.g. local dev without the registry running, or unit
tests) - this service keeps working standalone either way.
"""
import asyncio
import contextlib
import logging
import os

import httpx

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 10
REQUEST_TIMEOUT_S = 3.0


class RegistryClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self._instance_id: str | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _register(self, client: httpx.AsyncClient, name: str, host: str, port: int, health: str) -> str | None:
        try:
            resp = await client.post(
                f"{self.base_url}/register",
                json={"name": name, "host": host, "port": port, "health": health},
                timeout=REQUEST_TIMEOUT_S,
            )
            resp.raise_for_status()
            instance_id = resp.json()["instance_id"]
            logger.info("service-registry: registered as %s", instance_id)
            return instance_id
        except httpx.HTTPError as exc:
            logger.warning("service-registry: register failed: %s", exc)
            return None

    async def _loop(self, name: str, host: str, port: int, health: str) -> None:
        async with httpx.AsyncClient() as client:
            self._instance_id = await self._register(client, name, host, port, health)
            while not self._stop.is_set():
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=HEARTBEAT_INTERVAL_S)
                except asyncio.TimeoutError:
                    pass
                if self._stop.is_set():
                    break
                if self._instance_id is None:
                    self._instance_id = await self._register(client, name, host, port, health)
                    continue
                try:
                    resp = await client.post(
                        f"{self.base_url}/heartbeat/{self._instance_id}", timeout=REQUEST_TIMEOUT_S
                    )
                    if resp.status_code == 404:
                        logger.warning("service-registry: instance unknown, re-registering")
                        self._instance_id = await self._register(client, name, host, port, health)
                    elif resp.status_code >= 300:
                        logger.warning("service-registry: heartbeat failed: %s", resp.text)
                except httpx.HTTPError as exc:
                    logger.warning("service-registry: heartbeat error: %s", exc)

            if self._instance_id:
                with contextlib.suppress(httpx.HTTPError):
                    await client.delete(
                        f"{self.base_url}/deregister/{self._instance_id}", timeout=REQUEST_TIMEOUT_S
                    )
                logger.info("service-registry: deregistered %s", self._instance_id)

    def start(self, name: str, host: str, port: int, health: str) -> None:
        """Fire-and-forget background task: register, then heartbeat until stop()."""
        self._task = asyncio.create_task(self._loop(name, host, port, health))

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task


def register_if_configured(name: str, port: int, health: str) -> RegistryClient | None:
    """Start background registration if REGISTRY_URL is set; no-op otherwise.

    `port` is the address other services should dial this instance on (the
    gRPC port); `health` is a full HTTP health-check URL, which may be on a
    different port (the FastAPI/HTTP port).
    """
    base_url = os.getenv("REGISTRY_URL", "")
    if not base_url:
        logger.info("service-registry: REGISTRY_URL not set, skipping registration")
        return None
    host = os.getenv("SERVICE_HOST", name)
    client = RegistryClient(base_url)
    client.start(name, host, port, health)
    return client
