"""WhatsApp message handlers.

Normalize incoming WhatsApp updates to the canonical contract (ARCHITECTURE §5),
forward them to the core's /ingest, and render the canonical response back to
the user. This service is stateless — no business logic lives here.

Structure: pure `payload_from_*` builders (unit-testable, no I/O) + one
`process_update` coroutine that does the network round-trip. Handlers are
dispatched as background tasks from main.py so the webhook acks Meta fast.
"""

import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.services.core_client import CoreClient
from app.services.media import media_to_data_uri

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical payload builders (pure — no I/O)
# ---------------------------------------------------------------------------

def _contact_from(user) -> dict:
    """Map a PyWa user to a canonical contact (BSUID-first — see ARCHITECTURE §10)."""
    bsuid = getattr(user, "bsuid", None)
    wa_id = getattr(user, "wa_id", None)
    return {
        "external_id": bsuid or wa_id,  # BSUID is primary; wa_id is the fallback
        "wa_id": wa_id,
        "display_name": getattr(user, "name", None),
        "metadata": {},
    }


def _base_payload(update, mtype: str, *, text=None, media_url=None, raw=None) -> dict:
    ts = getattr(update, "timestamp", None)
    received_at = ts if isinstance(ts, datetime) else datetime.now(timezone.utc)
    return {
        "channel": "whatsapp",
        "contact": _contact_from(update.from_user),
        "message": {
            "type": mtype,
            "text": text,
            "media_url": media_url,
            "raw": raw or {},
        },
        "received_at": received_at.isoformat(),
    }


def _media_raw(update, media) -> dict:
    """Keep what a later sprint needs to download the media (URLs expire fast)."""
    return {
        "wamid": getattr(update, "id", None),
        "media_id": getattr(media, "id", None),
        "mime_type": getattr(media, "mime_type", None),
        "sha256": getattr(media, "sha256", None),
    }


def payload_from_text(msg) -> dict:
    return _base_payload(
        msg, "text", text=msg.text, raw={"wamid": getattr(msg, "id", None)}
    )


def payload_from_audio(msg) -> dict:
    raw = _media_raw(msg, msg.audio)
    raw["voice"] = bool(getattr(msg.audio, "voice", False))  # voice note vs audio file
    return _base_payload(msg, "audio", raw=raw)


def payload_from_image(msg) -> dict:
    return _base_payload(
        msg,
        "image",
        text=getattr(msg.image, "caption", None),
        raw=_media_raw(msg, msg.image),
    )


def payload_from_callback(cb) -> dict:
    """Quick-reply / interactive button press → canonical "button" message."""
    return _base_payload(
        cb,
        "button",
        text=getattr(cb, "title", None),
        raw={"wamid": getattr(cb, "id", None), "data": getattr(cb, "data", None)},
    )


# ---------------------------------------------------------------------------
# Processing (network) — runs as a background task, after Meta got its 200
# ---------------------------------------------------------------------------

async def _reply_canonical(update, result: dict) -> None:
    """Render the core's canonical response messages back to WhatsApp."""
    for m in result.get("messages", []):
        if m.get("type") == "text" and m.get("text"):
            await update.reply(m["text"], preview_url=True)
        else:
            # Outbound buttons/media land in a later sprint
            logger.warning("Skipping unsupported outbound message type: %s", m.get("type"))


async def process_update(update, core: CoreClient, payload: dict) -> None:
    """Canonical round-trip: typing indicator → /ingest → render reply."""
    try:
        await update.indicate_typing()
        result = await core.ingest(payload)
        if not result:
            await update.reply(settings.error_reply)
            return
        await _reply_canonical(update, result)
    except Exception:
        logger.exception("Failed processing update %s", getattr(update, "id", "?"))
        try:
            await update.reply(settings.error_reply)
        except Exception:  # pragma: no cover - best effort
            logger.exception("Could not deliver error reply")


# ---------------------------------------------------------------------------
# Handlers (thin: build payload → process)
# ---------------------------------------------------------------------------

async def handle_text_message(client, msg, core: CoreClient):
    await process_update(msg, core, payload_from_text(msg))


async def handle_audio_message(client, msg, core: CoreClient):
    payload = payload_from_audio(msg)
    # Inline the bytes so the (channel-agnostic) core can hear the audio now —
    # Meta media URLs expire in minutes and require the WA token.
    payload["message"]["media_url"] = await media_to_data_uri(msg.audio)
    await process_update(msg, core, payload)


async def handle_image_message(client, msg, core: CoreClient):
    payload = payload_from_image(msg)
    payload["message"]["media_url"] = await media_to_data_uri(msg.image)
    await process_update(msg, core, payload)


async def handle_callback_button(client, cb, core: CoreClient):
    await process_update(cb, core, payload_from_callback(cb))


async def handle_unsupported_message(client, msg):
    """Reply that this message type isn't supported yet."""
    logger.info("Unsupported message type '%s'", getattr(msg, "type", "?"))
    await msg.reply(settings.unsupported_reply)
