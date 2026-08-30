import pytest

from pack_manager.errors import ValidationError


PNG = b"\x89PNG\r\n\x1a\nexample"


def test_same_bytes_are_deduplicated(asset_store):
    first = asset_store.put_bytes("one.png", PNG, "image/png")
    second = asset_store.put_bytes("two.png", PNG, "image/png")

    assert first.id == second.id
    assert first.sha256 == second.sha256


def test_rejects_unsupported_mime(asset_store):
    with pytest.raises(ValidationError, match="unsupported image type"):
        asset_store.put_bytes("payload.txt", b"x", "text/plain")


def test_rejects_oversized_upload(asset_store):
    with pytest.raises(ValidationError, match="exceeds"):
        asset_store.put_bytes("huge.png", b"x" * 1025, "image/png")
