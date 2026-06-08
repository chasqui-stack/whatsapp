"""HTTP client for the Chasqui core. Posts canonical messages to /ingest."""

import logging

import httpx

logger = logging.getLogger(__name__)


class CoreClient:
    """Async client that forwards canonical messages to the core's /ingest."""

    def __init__(self, base_url: str, api_key: str):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=60.0)
        self.headers = {"X-Internal-API-Key": api_key} if api_key else {}

    async def ingest(self, payload: dict) -> dict | None:
        """POST a canonical message to the core. Returns the canonical response or None."""
        try:
            response = await self.client.post(
                "/ingest", json=payload, headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error("core /ingest error: %s", e)
            return None

    async def close(self) -> None:
        await self.client.aclose()
