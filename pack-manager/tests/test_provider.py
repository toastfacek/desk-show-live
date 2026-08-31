from pathlib import Path

import pytest

from pack_manager.providers import ReferenceCopyProvider


def test_reference_copy_provider_atomically_copies_first_reference(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    output = tmp_path / "generated" / "hero.png"

    result = ReferenceCopyProvider().generate_still(
        prompt="A clean wide shot",
        reference_paths=(first, second),
        seed=42,
        output_path=output,
    )

    assert result == output
    assert output.read_bytes() == b"first"
    assert list(output.parent.iterdir()) == [output]


def test_reference_copy_provider_requires_a_reference(tmp_path):
    with pytest.raises(ValueError, match="reference"):
        ReferenceCopyProvider().generate_still(
            prompt="A clean wide shot",
            reference_paths=(),
            seed=None,
            output_path=Path(tmp_path / "hero.png"),
        )
