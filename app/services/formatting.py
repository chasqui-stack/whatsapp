"""Render canonical Markdown → WhatsApp formatting.

The core emits one canonical markup (standard Markdown, ARCHITECTURE §5); each
gateway renders it to its platform. WhatsApp uses its own syntax — `*bold*`
(single star), `_italic_`, `~strike~`, `` `mono` `` / ``` ```block``` ``` — and
has no list/heading/link markup, so we map standard Markdown onto it.

Order matters: single-`*` italic is converted to `_..._` BEFORE `**bold**` is
collapsed to `*bold*`, otherwise the collapsed bold would be re-read as italic.
Best-effort and never raises; code spans are left as-is (WhatsApp renders
`` ` `` / ``` ``` ``` natively).
"""

import re


def to_whatsapp(text: str | None) -> str | None:
    if not text:
        return text
    # Bullets: leading "* "/"+ " → "- " (WhatsApp has no list syntax; "- " reads clean)
    text = re.sub(r"(?m)^([ \t]*)[*+][ \t]+", r"\1- ", text)
    # Italic: single-* emphasis (not part of **) → _.._  — BEFORE bold, so the
    # "*x*" that bold collapses to isn't re-read as italic.
    text = re.sub(r"(?<!\*)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\*)", r"_\1_", text)
    # Bold: **x** / __x__ → *x*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text, flags=re.S)
    text = re.sub(r"__(.+?)__", r"*\1*", text, flags=re.S)
    # Strikethrough: ~~x~~ → ~x~
    text = re.sub(r"~~(.+?)~~", r"~\1~", text, flags=re.S)
    # Links: [label](url) → label (url) — WhatsApp auto-links bare URLs
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", text)
    # Headings LAST: "### Title" → "*Title*" (the "*" it emits must survive the
    # italic pass above).
    text = re.sub(r"(?m)^#{1,6}[ \t]+(.+?)[ \t]*$", r"*\1*", text)
    return text
