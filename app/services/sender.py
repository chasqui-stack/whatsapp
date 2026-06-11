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

import base64
import logging

from pydantic import BaseModel, Field
from pywa.errors import ReEngagementMessage

logger = logging.getLogger(__name__)

MEDIA_TYPES = ("image", "document", "audio")


class SendContact(BaseModel):
    channel: str = "whatsapp"
    external_id: str | None = None
    wa_id: str | None = None


class SendMessage(BaseModel):
    type: str = "text"
    text: str | None = Field(default=None, max_length=4096)
    # base64 `data:` URI for image/document/audio — the exact mirror of the
    # inbound contract (the gateway can never fetch a core-private URL).
    media_url: str | None = None
    filename: str | None = None  # documents: what WhatsApp shows the user


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


def _decode_data_uri(uri: str) -> tuple[str, bytes]:
    """'data:<mime>;base64,<payload>' → (mime, bytes). Raises SendError."""
    header, _, payload = uri.partition(",")
    if not payload or not header.startswith("data:"):
        raise SendError(
            "INVALID_MEDIA", 422, "media_url must be a base64 data: URI"
        )
    mime = header.removeprefix("data:").split(";", 1)[0] or "application/octet-stream"
    try:
        return mime, base64.b64decode(payload)
    except Exception as exc:
        raise SendError("INVALID_MEDIA", 422, "media_url is not valid base64") from exc


async def _dispatch(wa, to: str, message: SendMessage):
    """Route one canonical message to the matching PyWa send call."""
    if message.type == "text":
        return await wa.send_message(to=to, text=message.text)

    mime, data = _decode_data_uri(message.media_url)
    if message.type == "image":
        return await wa.send_image(
            to=to, image=data, caption=message.text, mime_type=mime
        )
    if message.type == "document":
        return await wa.send_document(
            to=to,
            document=data,
            filename=message.filename or "document",
            caption=message.text,
            mime_type=mime,
        )
    # audio — voice notes and audio files alike
    return await wa.send_audio(to=to, audio=data, mime_type=mime)


async def send_canonical(wa, request: SendRequest) -> dict:
    """Render one canonical outbound message on WhatsApp. Raises SendError."""
    message = request.message
    if message.type == "text":
        if not message.text:
            raise SendError("UNSUPPORTED_TYPE", 422, "Text messages need text")
    elif message.type in MEDIA_TYPES:
        if not message.media_url:
            raise SendError(
                "UNSUPPORTED_TYPE", 422, f"{message.type} messages need media_url"
            )
    else:
        raise SendError(
            "UNSUPPORTED_TYPE",
            422,
            f"Unsupported outbound type '{message.type}' "
            f"(text, {', '.join(MEDIA_TYPES)})",
        )
    if not request.contact.wa_id:
        raise SendError(
            "NO_WA_ID",
            400,
            "The contact has no known WhatsApp number (wa_id) — "
            "Meta does not support sending by BSUID yet",
        )

    try:
        sent = await _dispatch(wa, request.contact.wa_id, message)
    except SendError:
        raise
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
