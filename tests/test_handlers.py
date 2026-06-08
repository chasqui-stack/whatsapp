"""Unit tests for canonical message normalization (no network)."""

from app.handlers.message_handlers import _contact_from


class FakeUser:
    def __init__(self, *, bsuid=None, wa_id=None, name=None):
        self.bsuid = bsuid
        self.wa_id = wa_id
        self.name = name


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
