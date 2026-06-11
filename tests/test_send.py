"""Unit tests for the canonical outbound seam (POST /send, ADR-004).

Same philosophy as test_handlers.py: the PyWa client is faked, no network.
"""

import pytest
from pywa.errors import ReEngagementMessage

from app.services.sender import SendError, SendRequest, send_canonical


def request(*, wa_id="51999888777", mtype="text", text="hola") -> SendRequest:
    return SendRequest.model_validate(
        {
            "contact": {"channel": "whatsapp", "external_id": "BSU123", "wa_id": wa_id},
            "message": {"type": mtype, "text": text},
        }
    )


class FakeSent:
    id = "wamid.SENT1"


class FakeWa:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.calls: list[dict] = []

    async def send_message(self, *, to, text):
        self.calls.append({"to": to, "text": text})
        if self.error:
            raise self.error
        return FakeSent()


def _reengagement() -> ReEngagementMessage:
    # Built the way PyWa builds it from a Meta API error payload (code 131047)
    return ReEngagementMessage(raw={}, code=131047, message="Re-engagement message")


async def test_send_text_via_wa_id():
    wa = FakeWa()

    result = await send_canonical(wa, request())

    assert result == {"status": "sent", "message_id": "wamid.SENT1"}
    assert wa.calls == [{"to": "51999888777", "text": "hola"}]


async def test_no_wa_id_is_a_clear_error():
    with pytest.raises(SendError) as exc:
        await send_canonical(FakeWa(), request(wa_id=None))
    assert exc.value.code == "NO_WA_ID"
    assert exc.value.status_code == 400


async def test_non_text_is_unsupported_for_now():
    with pytest.raises(SendError) as exc:
        await send_canonical(FakeWa(), request(mtype="image", text=None))
    assert exc.value.code == "UNSUPPORTED_TYPE"
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
