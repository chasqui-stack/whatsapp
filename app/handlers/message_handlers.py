"""WhatsApp message handlers.

Normalize incoming WhatsApp messages to the canonical contract, forward them
to the core's /ingest, and render the canonical response back to the user.
This service is stateless — no business logic lives here.
"""

import logging
from datetime import datetime, timezone

from pywa_async import WhatsApp, types

from app.services.core_client import CoreClient

logger = logging.getLogger(__name__)

ERROR_MSG = (
    "Disculpa, tuvimos un inconveniente técnico. "
    "Intenta de nuevo en unos minutos."
)
UNSUPPORTED_MSG = (
    "Por ahora solo proceso mensajes de texto. "
    "Envíame un texto y con gusto te ayudo \U0001f60a"
)


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


async def _reply_canonical(msg: types.Message, result: dict) -> None:
    """Render the core's canonical response messages back to WhatsApp."""
    for m in result.get("messages", []):
        if m.get("type") == "text" and m.get("text"):
            await msg.reply(m["text"], preview_url=True)


async def handle_text_message(client: WhatsApp, msg: types.Message, core: CoreClient):
    """Normalize a text message → core /ingest → reply."""
    payload = {
        "channel": "whatsapp",
        "contact": _contact_from(msg.from_user),
        "message": {
            "type": "text",
            "text": msg.text,
            "media_url": None,
            "raw": {},
        },
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    await msg.indicate_typing()
    result = await core.ingest(payload)
    if not result:
        await msg.reply(ERROR_MSG)
        return
    await _reply_canonical(msg, result)


async def handle_unsupported_message(client: WhatsApp, msg: types.Message):
    """Reply that only text is supported for now (media/buttons land in Sprint 2)."""
    logger.info("Unsupported message type '%s'", getattr(msg, "type", "?"))
    await msg.reply(UNSUPPORTED_MSG)
