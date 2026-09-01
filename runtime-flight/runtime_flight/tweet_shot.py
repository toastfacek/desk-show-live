"""Official-embed stills, cover-cropped to overlay wells.

The live X widget does not grow with the solo / card plates. Capture the
embed once, then crop. Fal never sees these files.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from runtime_flight.tweet_embed import TweetEmbedError, embed_frame_path

SHOT_W = 640
SHOT_H = 1400
PANEL = (21, 19, 15)
SPLIT_SIZE = (584, 628)
SOLO_SIZE = (1188, 628)
CARD_SIZE = (1792, 628)
SHOT_NAME = "tweet-shot.png"
SHOT_SPLIT_NAME = "tweet-shot-split.png"
SHOT_SOLO_NAME = "tweet-shot-solo.png"
SHOT_CARD_NAME = "tweet-shot-card.png"
WELL_CROP = {"x": 668, "y": 172, "w": 584, "h": 628}
# Eat the official card's rounded-corner panel wedges so cover-crop
# starts on tweet fill, not #15130F.
CARD_INSET = 10


class TweetShotError(Exception):
    """Raised when an official tweet still cannot be captured or cropped."""


def cover_crop(
    image: Image.Image,
    width: int,
    height: int,
    *,
    top: float = 0.0,
) -> Image.Image:
    if width < 1 or height < 1:
        raise TweetShotError("crop size must be positive")
    rgb = image.convert("RGB")
    scale = max(width / rgb.width, height / rgb.height)
    new_w = max(width, int(round(rgb.width * scale)))
    new_h = max(height, int(round(rgb.height * scale)))
    resized = rgb.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x = max(0, (new_w - width) // 2)
    y = max(0, min(new_h - height, int(round((new_h - height) * top))))
    return resized.crop((x, y, x + width, y + height))


def is_blank_panel(image: Image.Image, *, panel: tuple[int, int, int] = PANEL) -> bool:
    rgb = image.convert("RGB")
    pixels = rgb.load()
    total = rgb.width * rgb.height
    if total < 1:
        return True
    matches = 0
    for y in range(rgb.height):
        for x in range(rgb.width):
            if pixels[x, y] == panel:
                matches += 1
    return matches / total > 0.98


def _is_panel(
    pixel: tuple[int, int, int],
    panel: tuple[int, int, int],
    slop: int,
) -> bool:
    return all(abs(int(a) - int(b)) <= slop for a, b in zip(pixel, panel))


def trim_panel(
    image: Image.Image,
    *,
    panel: tuple[int, int, int] = PANEL,
    slop: int = 6,
) -> Image.Image:
    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size

    def row_empty(y: int) -> bool:
        return all(_is_panel(pixels[x, y], panel, slop) for x in range(width))

    def col_empty(x: int) -> bool:
        return all(_is_panel(pixels[x, y], panel, slop) for y in range(height))

    top = 0
    while top < height and row_empty(top):
        top += 1
    bottom = height - 1
    while bottom >= top and row_empty(bottom):
        bottom -= 1
    left = 0
    while left < width and col_empty(left):
        left += 1
    right = width - 1
    while right >= left and col_empty(right):
        right -= 1
    if top > bottom or left > right:
        return rgb
    return rgb.crop((left, top, right + 1, bottom + 1))


def write_shot_set(image: Image.Image, dest: Path) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    full = dest / SHOT_NAME
    split = dest / SHOT_SPLIT_NAME
    solo = dest / SHOT_SOLO_NAME
    card = dest / SHOT_CARD_NAME
    trimmed = trim_panel(image)
    if (
        trimmed.width > CARD_INSET * 2
        and trimmed.height > CARD_INSET * 2
    ):
        trimmed = trimmed.crop(
            (
                CARD_INSET,
                CARD_INSET,
                trimmed.width - CARD_INSET,
                trimmed.height - CARD_INSET,
            )
        )
    trimmed.save(full, format="PNG")
    cover_crop(trimmed, *SPLIT_SIZE).save(split, format="PNG")
    cover_crop(trimmed, *SOLO_SIZE).save(solo, format="PNG")
    cover_crop(trimmed, *CARD_SIZE).save(card, format="PNG")
    return {"full": full, "split": split, "solo": solo, "card": card}


def crop_program_well(
    program: Image.Image,
    *,
    x: int = WELL_CROP["x"],
    y: int = WELL_CROP["y"],
    w: int = WELL_CROP["w"],
    h: int = WELL_CROP["h"],
) -> Image.Image:
    rgb = program.convert("RGB")
    box = (x, y, x + w, y + h)
    if box[2] > rgb.width or box[3] > rgb.height:
        raise TweetShotError("program still is smaller than the card well")
    return rgb.crop(box)


def find_chrome() -> str:
    for name in (
        "google-chrome-stable",
        "google-chrome",
        "chromium-browser",
        "chromium",
    ):
        path = shutil.which(name)
        if path:
            return path
    raise TweetShotError("chrome is not on PATH")


def capture_embed_shot(
    embed_url: str,
    dest: Path,
    *,
    chrome: str | None = None,
    width: int = SHOT_W,
    height: int = SHOT_H,
    timeout_s: float = 30.0,
) -> Path:
    if not embed_url.startswith(("http://127.0.0.1", "http://localhost")):
        raise TweetShotError("embed capture must stay on loopback")
    chrome = chrome or find_chrome()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tweet-shot-") as raw_dir:
        raw = Path(raw_dir) / "raw.png"
        completed = subprocess.run(
            [
                chrome,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-sandbox",
                "--force-device-scale-factor=1",
                f"--window-size={int(width)},{int(height)}",
                f"--screenshot={raw}",
                "--virtual-time-budget=12000",
                embed_url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if completed.returncode != 0 or not raw.is_file():
            raise TweetShotError(
                completed.stderr.strip() or "chrome did not write a tweet still"
            )
        image = Image.open(raw)
        if is_blank_panel(image):
            raise TweetShotError("chrome tweet still is an empty panel")
        write_shot_set(image, dest)
    return dest / SHOT_NAME


def capture_from_overlay(
    overlay_url: str,
    tweet_id: str,
    dest: Path,
    **kwargs,
) -> Path:
    if not tweet_id.isdigit():
        raise TweetEmbedError("tweet id is not a numeric status id")
    base = overlay_url.rstrip("/")
    return capture_embed_shot(base + embed_frame_path(tweet_id), dest, **kwargs)


def png_bytes(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
