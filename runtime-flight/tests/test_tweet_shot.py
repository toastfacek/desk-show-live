"""Official tweet stills cover-crop into overlay wells."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from runtime_flight.tweet_shot import (
    CARD_SIZE,
    SOLO_SIZE,
    SPLIT_SIZE,
    cover_crop,
    crop_program_well,
    trim_panel,
    write_shot_set,
)


def _plate(width: int, height: int, *, mark: tuple[int, int, int] = (40, 80, 200)) -> Image.Image:
    image = Image.new("RGB", (width, height), (21, 19, 15))
    image.paste(Image.new("RGB", (width, 80), mark), (0, 0))
    return image


def test_cover_crop_fills_the_solo_well_from_the_top() -> None:
    source = _plate(584, 628)
    solo = cover_crop(source, *SOLO_SIZE)
    assert solo.size == SOLO_SIZE
    assert solo.getpixel((0, 0)) == (40, 80, 200)
    assert solo.getpixel((SOLO_SIZE[0] // 2, 20)) == (40, 80, 200)


def test_cover_crop_and_well_extract_write_the_shot_set(tmp_path: Path) -> None:
    program = Image.new("RGB", (1920, 1080), (11, 10, 8))
    well = Image.new("RGB", (584, 628), (30, 40, 50))
    well.paste(Image.new("RGB", (584, 120), (200, 40, 40)), (0, 0))
    program.paste(well, (668, 172))
    extracted = crop_program_well(program)
    assert extracted.size == (584, 628)
    assert extracted.getpixel((10, 10)) == (200, 40, 40)
    paths = write_shot_set(extracted, tmp_path)
    assert Image.open(paths["split"]).size == SPLIT_SIZE
    assert Image.open(paths["solo"]).size == SOLO_SIZE
    assert Image.open(paths["card"]).size == CARD_SIZE


def test_trim_panel_drops_empty_bottom() -> None:
    image = Image.new("RGB", (100, 200), (21, 19, 15))
    image.paste(Image.new("RGB", (100, 40), (9, 9, 9)), (0, 0))
    trimmed = trim_panel(image)
    assert trimmed.size == (100, 40)
