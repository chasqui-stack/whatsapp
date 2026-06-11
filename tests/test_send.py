"""Unit tests for the canonical outbound seam (POST /send, ADR-004).

Same philosophy as test_handlers.py: the PyWa client is faked, no network.
"""

import pytest
from pywa.errors import ReEngagementMessage

from app.services.sender import SendError, SendRequest, send_canonical


import base64

JPEG_URI = "data:image/jpeg;base64," + base64.b64encode(b"fake-jpeg").decode()


def request(
    *, wa_id="51999888777", mtype="text", text="hola", media_url=None, filename=None
) -> SendRequest:
    return SendRequest.model_validate(
        {
            "contact": {"channel": "whatsapp", "external_id": "BSU123", "wa_id": wa_id},
            "message": {
                "type": mtype,
                "text": text,
                "media_url": media_url,
                "filename": filename,
            },
        }
    )


class FakeSent:
    id = "wamid.SENT1"


class FakeWa:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict] = []

    def _record(self, method: str, kwargs: dict):
        self.calls.append({"method": method, **kwargs})
        if self.error:
            raise self.error
        return FakeSent()

    async def send_message(self, *, to, text):
        return self._record("send_message", {"to": to, "text": text})

    async def send_image(self, *, to, image, caption=None, mime_type=None):
        return self._record(
            "send_image",
            {"to": to, "image": image, "caption": caption, "mime_type": mime_type},
        )

    async def send_document(
        self, *, to, document, filename=None, caption=None, mime_type=None
    ):
        return self._record(
            "send_document",
            {"to": to, "document": document, "filename": filename,
             "caption": caption, "mime_type": mime_type},
        )

    async def upload_media(self, *, media, mime_type=None, filename=None):
        return self._record(
            "upload_media",
            {"media": media, "mime_type": mime_type, "filename": filename},
        )

    async def send_audio(self, *, to, audio):
        return self._record("send_audio", {"to": to, "audio": audio})


def _reengagement() -> ReEngagementMessage:
    # Built the way PyWa builds it from a Meta API error payload (code 131047)
    return ReEngagementMessage(raw={}, code=131047, message="Re-engagement message")


async def test_send_text_via_wa_id():
    wa = FakeWa()

    result = await send_canonical(wa, request())

    assert result == {"status": "sent", "message_id": "wamid.SENT1"}
    assert wa.calls == [
        {"method": "send_message", "to": "51999888777", "text": "hola"}
    ]


async def test_no_wa_id_is_a_clear_error():
    with pytest.raises(SendError) as exc:
        await send_canonical(FakeWa(), request(wa_id=None))
    assert exc.value.code == "NO_WA_ID"
    assert exc.value.status_code == 400


async def test_send_image_with_caption():
    wa = FakeWa()

    await send_canonical(
        wa, request(mtype="image", text="mira esto", media_url=JPEG_URI)
    )

    call = wa.calls[0]
    assert call["method"] == "send_image"
    assert call["image"] == b"fake-jpeg"
    assert call["caption"] == "mira esto"
    assert call["mime_type"] == "image/jpeg"


async def test_send_document_with_filename():
    wa = FakeWa()
    pdf_uri = "data:application/pdf;base64," + base64.b64encode(b"%PDF-fake").decode()

    await send_canonical(
        wa,
        request(mtype="document", text=None, media_url=pdf_uri, filename="recibo.pdf"),
    )

    call = wa.calls[0]
    assert call["method"] == "send_document"
    assert call["document"] == b"%PDF-fake"
    assert call["filename"] == "recibo.pdf"
    assert call["mime_type"] == "application/pdf"


async def test_mp3_audio_goes_out_untouched():
    wa = FakeWa()
    audio_uri = "data:audio/mpeg;base64," + base64.b64encode(b"ID3-mp3").decode()

    await send_canonical(wa, request(mtype="audio", text=None, media_url=audio_uri))

    upload, send = wa.calls
    # Explicit upload with a filename matching the content — Meta fails
    # filename/content mismatches asynchronously as octet-stream
    assert upload["method"] == "upload_media"
    assert upload["media"] == b"ID3-mp3"
    assert upload["mime_type"] == "audio/mpeg"
    assert upload["filename"] == "voice.mp3"
    assert send["method"] == "send_audio"


async def test_browser_audio_is_transcoded_to_mp3(monkeypatch):
    # Everything MediaRecorder produces (opus-in-mp4, AAC fragmented mp4,
    # webm — and even valid OGG) failed live; MP3 is the production-proven
    # format, so all non-mp3 audio is normalized to it.
    from app.services import sender

    async def fake_transcode(data):
        assert data == b"fragmented-mp4-aac"
        return b"ID3-transcoded"

    monkeypatch.setattr(sender, "_transcode_to_mp3", fake_transcode)
    wa = FakeWa()
    uri = "data:audio/mp4;base64," + base64.b64encode(b"fragmented-mp4-aac").decode()

    await send_canonical(wa, request(mtype="audio", text=None, media_url=uri))

    upload, send = wa.calls
    assert upload["media"] == b"ID3-transcoded"
    assert upload["mime_type"] == "audio/mpeg"
    assert upload["filename"] == "voice.mp3"


async def test_transcode_failure_sends_original(monkeypatch):
    from app.services import sender

    # No ffmpeg on PATH → best-effort passthrough
    monkeypatch.setattr(sender.shutil, "which", lambda _: None)
    wa = FakeWa()
    webm = b"\x1aE\xdf\xa3fake-webm"
    uri = "data:audio/webm;base64," + base64.b64encode(webm).decode()

    await send_canonical(wa, request(mtype="audio", text=None, media_url=uri))

    upload, send = wa.calls
    assert upload["media"] == webm
    assert upload["mime_type"] == "audio/webm"
    assert upload["filename"] == "voice.bin"


async def test_media_type_without_media_url_is_unsupported():
    with pytest.raises(SendError) as exc:
        await send_canonical(FakeWa(), request(mtype="image", text=None))
    assert exc.value.code == "UNSUPPORTED_TYPE"
    assert exc.value.status_code == 422


async def test_unknown_type_is_unsupported():
    with pytest.raises(SendError) as exc:
        await send_canonical(FakeWa(), request(mtype="video", text=None))
    assert exc.value.code == "UNSUPPORTED_TYPE"


async def test_malformed_data_uri_is_invalid_media():
    with pytest.raises(SendError) as exc:
        await send_canonical(
            FakeWa(), request(mtype="image", text=None, media_url="https://x/y.jpg")
        )
    assert exc.value.code == "INVALID_MEDIA"
    assert exc.value.status_code == 422


async def test_reengagement_maps_to_window_expired():
    with pytest.raises(SendError) as exc:
        await send_canonical(FakeWa(error=_reengagement()), request())
    assert exc.value.code == "WINDOW_EXPIRED"
    assert exc.value.status_code == 502


async def test_other_failures_map_to_send_failed():
    with pytest.raises(SendError) as exc:
        await send_canonical(FakeWa(error=RuntimeError("api down")), request())
    assert exc.value.code == "SEND_FAILED"
    assert exc.value.status_code == 502
