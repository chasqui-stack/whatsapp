"""Unit tests for media → data URI inlining (no network)."""

import base64
from pathlib import Path

from app.services.media import MAX_MEDIA_BYTES, media_to_data_uri


class FakeDownloadableMedia:
    def __init__(self, data: bytes = b"fake-ogg-bytes", mime="audio/ogg", fail=False):
        self.id = "media-123"
        self.mime_type = mime
        self._data = data
        self._fail = fail

    async def download(self, *, path=None, **kwargs):
        if self._fail:
            raise RuntimeError("network down")
        target = Path(path) / "media.bin"
        target.write_bytes(self._data)
        return target


async def test_media_becomes_self_contained_data_uri():
    uri = await media_to_data_uri(FakeDownloadableMedia())
    expected_b64 = base64.b64encode(b"fake-ogg-bytes").decode()
    assert uri == f"data:audio/ogg;base64,{expected_b64}"


async def test_download_failure_returns_none_never_raises():
    assert await media_to_data_uri(FakeDownloadableMedia(fail=True)) is None


async def test_oversized_media_is_skipped():
    big = FakeDownloadableMedia(data=b"x" * (MAX_MEDIA_BYTES + 1))
    assert await media_to_data_uri(big) is None


async def test_missing_mime_falls_back_to_octet_stream():
    media = FakeDownloadableMedia(mime=None)
    uri = await media_to_data_uri(media)
    assert uri.startswith("data:application/octet-stream;base64,")
