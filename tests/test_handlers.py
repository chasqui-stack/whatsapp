"""Unit tests for canonical message normalization (no network)."""

from datetime import datetime, timezone

from app.handlers.message_handlers import (
    _contact_from,
    payload_from_audio,
    payload_from_callback,
    payload_from_image,
    payload_from_text,
)

CANONICAL_KEYS = {"channel", "contact", "message", "received_at"}
MESSAGE_KEYS = {"type", "text", "media_url", "raw"}


class FakeUser:
    def __init__(self, *, bsuid=None, wa_id=None, name=None):
        self.bsuid = bsuid
        self.wa_id = wa_id
        self.name = name


class FakeMedia:
    def __init__(self, *, id="media-1", mime_type="application/octet-stream",
                 sha256="abc", caption=None, voice=False):
        self.id = id
        self.mime_type = mime_type
        self.sha256 = sha256
        self.caption = caption
        self.voice = voice


class FakeMessage:
    def __init__(self, *, text=None, audio=None, image=None, user=None):
        self.id = "wamid.TEST1"
        self.text = text
        self.audio = audio
        self.image = image
        self.from_user = user or FakeUser(bsuid="BSU123", wa_id="51999888777", name="Juan")
        self.timestamp = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


class FakeCallback:
    def __init__(self):
        self.id = "wamid.CB1"
        self.title = "Sí, quiero"
        self.data = "confirm_yes"
        self.from_user = FakeUser(bsuid="BSU123", name="Juan")
        self.timestamp = datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


# --- contact mapping (BSUID-first, §10) ---

def test_contact_prefers_bsuid():
    contact = _contact_from(FakeUser(bsuid="BSU123", wa_id="51999888777", name="Juan"))
    assert contact["external_id"] == "BSU123"
    assert contact["wa_id"] == "51999888777"
    assert contact["display_name"] == "Juan"


def test_contact_falls_back_to_wa_id():
    contact = _contact_from(FakeUser(bsuid=None, wa_id="51999888777"))
    assert contact["external_id"] == "51999888777"


def test_contact_shape():
    contact = _contact_from(FakeUser(bsuid="BSU1"))
    assert set(contact.keys()) == {"external_id", "wa_id", "display_name", "metadata"}
    assert contact["metadata"] == {}


# --- canonical payload builders (§5) ---

def test_text_payload_canonical_shape():
    payload = payload_from_text(FakeMessage(text="Hola"))
    assert set(payload.keys()) == CANONICAL_KEYS
    assert set(payload["message"].keys()) == MESSAGE_KEYS
    assert payload["channel"] == "whatsapp"
    assert payload["message"]["type"] == "text"
    assert payload["message"]["text"] == "Hola"
    assert payload["message"]["raw"]["wamid"] == "wamid.TEST1"
    assert payload["received_at"] == "2026-06-09T12:00:00+00:00"


def test_audio_payload_keeps_media_id_for_later_download():
    msg = FakeMessage(audio=FakeMedia(id="audio-9", mime_type="audio/ogg", voice=True))
    payload = payload_from_audio(msg)
    assert payload["message"]["type"] == "audio"
    assert payload["message"]["text"] is None
    assert payload["message"]["media_url"] is None  # URLs expire; media_id is kept
    assert payload["message"]["raw"]["media_id"] == "audio-9"
    assert payload["message"]["raw"]["voice"] is True


def test_image_payload_maps_caption_to_text():
    msg = FakeMessage(image=FakeMedia(id="img-7", mime_type="image/jpeg", caption="mi recibo"))
    payload = payload_from_image(msg)
    assert payload["message"]["type"] == "image"
    assert payload["message"]["text"] == "mi recibo"
    assert payload["message"]["raw"]["media_id"] == "img-7"


def test_callback_payload_maps_button():
    payload = payload_from_callback(FakeCallback())
    assert payload["message"]["type"] == "button"
    assert payload["message"]["text"] == "Sí, quiero"
    assert payload["message"]["raw"]["data"] == "confirm_yes"
    assert payload["contact"]["external_id"] == "BSU123"
