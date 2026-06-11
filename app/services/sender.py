"""Canonical outbound sending (ADR-004) — the gateway side of `POST /send`.

The mirror of /ingest: the core POSTs a canonical message here and this
service renders it on WhatsApp via PyWa. Addressing is `wa_id`-based — Meta
has no BSUID send endpoint yet (the Sprint 2 gotcha), so contacts without a
known wa_id can't be messaged (`NO_WA_ID`).

Error codes are part of the contract: WhatsApp's 24h customer-service
window makes Meta reject free-form messages sent too late — PyWa raises
ReEngagementMessage (error 131047), mapped to `WINDOW_EXPIRED` so the admin
panel can explain it. Caveat: Meta sometimes accepts the message and fails
it asynchronously via a status webhook; this mapping is best-effort.
"""

import logging

from pydantic import BaseModel, Field
from pywa.errors import ReEngagementMessage

logger = logging.getLogger(__name__)


class SendContact(BaseModel):
    channel: str = "whatsapp"
    external_id: str | None = None
    wa_id: str | None = None


class SendMessage(BaseModel):
    type: str = "text"
    text: str | None = Field(default=None, max_length=4096)


class SendRequest(BaseModel):
    contact: SendContact
    message: SendMessage


class SendError(Exception):
    """A send that didn't happen — `code` travels back to the core verbatim."""

    def __init__(self, code: str, status_code: int, message: str):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message


async def send_canonical(wa, request: SendRequest) -> dict:
    """Render one canonical outbound message on WhatsApp. Raises SendError."""
    if request.message.type != "text" or not request.message.text:
        raise SendError(
            "UNSUPPORTED_TYPE", 422, "Only text messages are supported for now"
        )
    if not request.contact.wa_id:
        raise SendError(
            "NO_WA_ID",
            400,
            "The contact has no known WhatsApp number (wa_id) — "
            "Meta does not support sending by BSUID yet",
        )

    try:
        sent = await wa.send_message(to=request.contact.wa_id, text=request.message.text)
    except ReEngagementMessage as exc:
        logger.warning("24h window expired for %s: %s", request.contact.wa_id, exc)
        raise SendError(
            "WINDOW_EXPIRED",
            502,
            "Outside WhatsApp's 24h customer-service window — "
            "the user must write first",
        ) from exc
    except Exception as exc:
        logger.exception("WhatsApp send failed for %s", request.contact.wa_id)
        raise SendError("SEND_FAILED", 502, f"WhatsApp send failed: {exc}") from exc

    return {"status": "sent", "message_id": str(getattr(sent, "id", sent))}
