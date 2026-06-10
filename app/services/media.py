"""Media download — turn WhatsApp media into a self-contained data URI.

Meta's media URLs expire in minutes and need the WA token, so the core (which
is channel-agnostic) can never fetch them. The gateway downloads the bytes
and ships them inline in the canonical `media_url` as `data:<mime>;base64,…`.
The core uses them for the current LLM turn only (history stays text-only).
"""

import base64
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# WhatsApp caps: images 5 MB, audio 16 MB — anything beyond is suspicious
MAX_MEDIA_BYTES = 16 * 1024 * 1024


async def media_to_data_uri(media) -> str | None:
    """Download a PyWa media object → data URI (None on failure, never raises)."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = await media.download(path=tmp)
            data = Path(path).read_bytes()
    except Exception:
        logger.warning(
            "Media download failed (id=%s)", getattr(media, "id", "?"), exc_info=True
        )
        return None

    if len(data) > MAX_MEDIA_BYTES:
        logger.warning(
            "Media too large (%d bytes, id=%s) — skipping inline payload",
            len(data),
            getattr(media, "id", "?"),
        )
        return None

    mime = getattr(media, "mime_type", None) or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"
