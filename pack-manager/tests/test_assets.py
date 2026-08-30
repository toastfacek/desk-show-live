import pytest

from pack_manager.errors import ValidationError


PNG = b"\x89PNG\r\n\x1a\nexample"


def test_same_bytes_are_deduplicated(asset_store):
    first = asset_store.put_bytes("one.png", PNG, "image/png")
    second = asset_store.put_bytes("two.png", PNG, "image/png")

    assert first.id == second.id
    assert first.sha256 == second.sha256


def test_same_bytes_with_different_mime_keep_one_canonical_blob(asset_store):
    first = asset_store.put_bytes("one.png", PNG, "image/png")
    second = asset_store.put_bytes("one.webp", PNG, "image/webp")

    assert second == first
    assert second.mime_type == "image/png"
    assert second.path.suffix == ".png"
    assert list((asset_store.data_dir / "blobs").iterdir()) == [first.path]


def test_get_round_trips_asset(asset_store):
    stored = asset_store.put_bytes("one.png", PNG, "image/png")

    assert asset_store.get(stored.id) == stored


@pytest.mark.parametrize(
    ("filename", "content", "mime_type", "suffix"),
    [
        ("photo.jpg", b"jpeg-content", "image/jpeg", ".jpg"),
        ("photo.webp", b"webp-content", "image/webp", ".webp"),
    ],
)
def test_accepts_supported_image_types(
    asset_store, filename, content, mime_type, suffix
):
    asset = asset_store.put_bytes(filename, content, mime_type)

    assert asset.mime_type == mime_type
    assert asset.path.suffix == suffix
    assert asset.path.read_bytes() == content


def test_rejects_unsupported_mime(asset_store):
    with pytest.raises(ValidationError, match="unsupported image type"):
        asset_store.put_bytes("payload.txt", b"x", "text/plain")


def test_rejects_oversized_upload(asset_store):
    with pytest.raises(ValidationError, match="exceeds"):
        asset_store.put_bytes("huge.png", b"x" * 1025, "image/png")
