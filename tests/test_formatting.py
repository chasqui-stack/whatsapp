"""Canonical Markdown → WhatsApp syntax."""

from app.services.formatting import to_whatsapp


def test_bold_double_star_to_single():
    assert to_whatsapp("hello **world**") == "hello *world*"


def test_bold_double_underscore_to_single_star():
    assert to_whatsapp("__strong__") == "*strong*"


def test_italic_single_star_to_underscore():
    assert to_whatsapp("an *emphasis* here") == "an _emphasis_ here"


def test_single_underscore_italic_kept():
    assert to_whatsapp("already _italic_") == "already _italic_"


def test_bold_and_italic_together():
    # ** must become * (bold) and the single * must become _ (italic)
    assert to_whatsapp("**bold** and *it*") == "*bold* and _it_"


def test_heading_becomes_bold():
    assert to_whatsapp("### Title") == "*Title*"


def test_bullets_become_dashes():
    assert to_whatsapp("* one\n* two") == "- one\n- two"


def test_strikethrough():
    assert to_whatsapp("~~gone~~") == "~gone~"


def test_link_becomes_label_and_url():
    assert to_whatsapp("see [the docs](https://x.io/a)") == "see the docs (https://x.io/a)"


def test_empty_and_none_passthrough():
    assert to_whatsapp("") == ""
    assert to_whatsapp(None) is None
