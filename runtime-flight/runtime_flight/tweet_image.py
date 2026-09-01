"""Render a 584×660 tweet / producer-card PNG. 1080 furniture, never sent to fal."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CARD_W = 584
CARD_H = 660
INK = (11, 10, 8)
PANEL = (21, 19, 15)
BONE = (244, 241, 234)
BONE_2 = (173, 166, 154)
BONE_3 = (107, 101, 92)
LEMON = (212, 224, 74)

_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
_SANS = _FONT_DIR / "DejaVuSans.ttf"
_SANS_BOLD = _FONT_DIR / "DejaVuSans-Bold.ttf"
_MONO = _FONT_DIR / "DejaVuSansMono-Bold.ttf"
_CJK_FONTS = (
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
)


class TweetImageError(Exception):
    """Raised when the tweet card image cannot be rendered."""


def render_tweet_card(
    *,
    author: str,
    text: str,
    media_path: Path | None = None,
) -> bytes:
    if not author or not text:
        raise TweetImageError("author and text are required")
    image = Image.new("RGB", (CARD_W, CARD_H), PANEL)
    draw = ImageDraw.Draw(image)
    handle = author if author.startswith("@") else f"@{author}"
    pad = 30
    y = 32
    badge = "POST"
    badge_font = _font(_MONO, 22)
    badge_box = draw.textbbox((0, 0), badge, font=badge_font)
    badge_w = badge_box[2] - badge_box[0] + 22
    badge_h = badge_box[3] - badge_box[1] + 16
    draw.rectangle((pad, y, pad + badge_w, y + badge_h), fill=LEMON)
    draw.text((pad + 11, y + 7), badge, font=badge_font, fill=INK)
    draw.text((pad + badge_w + 14, y + 8), handle, font=_font(_MONO, 20), fill=BONE_3)
    y += badge_h + 22

    photo = _load_media(media_path)
    text_budget = CARD_H - y - 72
    if photo is not None:
        max_photo_h = 280
        fitted = _fit_contain(photo, CARD_W - pad * 2, max_photo_h)
        image.paste(fitted, (pad, y))
        y += fitted.height + 20
        text_budget = CARD_H - y - 72

    body_font = _body_font(28, text)
    lines = _wrap(draw, text, body_font, CARD_W - pad * 2)
    line_h = 36
    max_lines = max(1, text_budget // line_h)
    shown = lines[:max_lines]
    if len(lines) > max_lines:
        shown = lines[: max_lines - 1] + [_ellipsis(draw, lines[max_lines - 1], body_font, CARD_W - pad * 2)]
    for line in shown:
        draw.text((pad, y), line, font=body_font, fill=BONE)
        y += line_h

    draw.text((pad, CARD_H - 46), "RUNTIME", font=_font(_MONO, 18), fill=BONE_3)
    draw.text((CARD_W - pad - 70, CARD_H - 46), "CARD", font=_font(_MONO, 18), fill=BONE_3)
    return _png_bytes(image)


def _load_media(path: Path | None) -> Image.Image | None:
    if path is None:
        return None
    try:
        with Image.open(path) as opened:
            return opened.convert("RGB")
    except OSError as error:
        raise TweetImageError("tweet media is not a readable image") from error


def _fit_contain(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    copy = image.copy()
    copy.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    return copy


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.replace("\r", "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(draw, candidate, font) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _ellipsis(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    width: int,
) -> str:
    suffix = "…"
    if _text_width(draw, text + suffix, font) <= width:
        return text + suffix
    trimmed = text
    while trimmed and _text_width(draw, trimmed + suffix, font) > width:
        trimmed = trimmed[:-1]
    return (trimmed or "") + suffix


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _body_font(size: int, text: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if _has_cjk(text):
        for path in _CJK_FONTS:
            if not path.is_file():
                continue
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return _font(_SANS_BOLD, size)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if path.is_file():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _png_bytes(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
