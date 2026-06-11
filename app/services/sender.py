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

import asyncio
import base64
import logging
import shutil

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


def _is_opus_outside_ogg(mime: str, data: bytes) -> bool:
    """WhatsApp only accepts Opus inside OGG (and AAC inside m4a) — browser
    recorders (MediaRecorder) produce Opus in WebM or even in MP4, which
    Meta accepts with a 200 and then REJECTS asynchronously via a status
    webhook. Detect it so we can remux before Meta ever sees it."""
    if mime == "audio/webm":
        return True
    # Opus-in-MP4: the moov sample description carries the 'Opus' fourcc
    return mime == "audio/mp4" and b"Opus" in data[:8192]


async def _remux_opus_to_ogg(data: bytes) -> bytes | None:
    """Repackage Opus into an OGG container with ffmpeg (`-c:a copy` — pure
    remux, no re-encode, milliseconds). Best-effort: no ffmpeg or a remux
    failure returns None and the original bytes go out as-is."""
    if shutil.which("ffmpeg") is None:
        logger.warning(
            "Opus audio in an unsupported container and no ffmpeg on PATH — "
            "sending as-is (Meta will likely reject it asynchronously)"
        )
        return None
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0", "-c:a", "copy", "-f", "ogg", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(data)
    if proc.returncode != 0 or not out:
        logger.warning(
            "ffmpeg remux failed — sending original audio: %s",
            err.decode(errors="replace")[:200],
        )
        return None
    return out


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
    # audio — remux browser-recorded Opus into OGG (the one container Meta
    # accepts it in); a successful remux ships as a real voice note
    is_voice = None
    if _is_opus_outside_ogg(mime, data):
        remuxed = await _remux_opus_to_ogg(data)
        if remuxed is not None:
            mime, data, is_voice = "audio/ogg", remuxed, True
    return await wa.send_audio(to=to, audio=data, mime_type=mime, is_voice=is_voice)


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
