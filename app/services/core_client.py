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

    async def notify_status(
        self, message_id: str, status: str, code: str | None, detail: str | None
    ) -> None:
        """Forward an async delivery status (e.g. Meta's late rejection of an
        accepted send) to the core so the admin panel can surface it."""
        try:
            response = await self.client.post(
                "/channel/status",
                json={
                    "message_id": message_id,
                    "status": status,
                    "code": code,
                    "detail": detail,
                },
                headers=self.headers,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error("core /channel/status error: %s", e)

    async def close(self) -> None:
        await self.client.aclose()
