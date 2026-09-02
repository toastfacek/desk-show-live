"""Deterministic H3 prompt assembly from locked v2 pack fields."""

from __future__ import annotations

import unicodedata
from typing import Any, Literal, Mapping

from runtime_flight.baseline import BaselineContext, CharacterPackTruth

MAX_LINE_CHARS = 120
SPEAKERS = frozenset({"BOT1", "BOT2"})


class PromptError(Exception):
    """Raised when a generation prompt cannot be assembled."""


def assemble_prompt(
    baseline: BaselineContext,
    speaker: Literal["BOT1", "BOT2"],
    line: str,
    max_line_chars: int = MAX_LINE_CHARS,
) -> str:
    if speaker not in SPEAKERS:
        raise PromptError("speaker must be BOT1 or BOT2")
    cleaned = _require_line(line, max_line_chars=max_line_chars)
    bot1 = _character(baseline, "BOT1")
    bot2 = _character(baseline, "BOT2")
    active = bot1 if speaker == "BOT1" else bot2
    scene = baseline.scene.manifest
    return "\n".join(
        (
            "Original flat 2D animated live-show shot.",
            f"Scene: {_require_str(scene.get('set'), 'set')}",
            f"Palette: {_format_palette(scene.get('palette'))}",
            f"Lighting: {_require_str(scene.get('lighting'), 'lighting')}",
            "Camera: locked wide eye-level two-shot, BOT1 left, BOT2 right, no camera movement.",
            f"BOT1: {_host_line(bot1)}",
            f"BOT2: {_host_line(bot2)}",
            f"Active host voice: {_require_str(active.manifest.get('voice_direction'), 'voice_direction')}",
            f"Action: {speaker} speaks while the other host listens with small eye and body reactions.",
            f'Dialogue: "{_escape_quotes(cleaned)}"',
            "No readable text, letters, numbers, logos, captions, lower thirds, or UI inside the generated frame.",
        )
    )


def _character(baseline: BaselineContext, slot: Literal["BOT1", "BOT2"]) -> CharacterPackTruth:
    for character in baseline.characters:
        if character.slot == slot:
            return character
    raise PromptError(f"baseline is missing {slot}")


def _host_line(character: CharacterPackTruth) -> str:
    invariants = character.manifest.get("visual_invariants")
    if not isinstance(invariants, Mapping):
        raise PromptError("visual_invariants must be an object")
    silhouette = _require_str(invariants.get("silhouette"), "silhouette")
    eyes = _require_str(invariants.get("eye_design"), "eye_design")
    proportions = _require_str(invariants.get("proportions"), "proportions")
    return f"{silhouette}; eyes: {eyes}; proportions: {proportions}."


def _format_palette(value: Any) -> str:
    if isinstance(value, str):
        return _require_str(value, "palette")
    if isinstance(value, (list, tuple)):
        parts = [_require_str(item, "palette") for item in value]
        if not parts:
            raise PromptError("palette must be a non-empty string")
        return ", ".join(parts)
    raise PromptError("palette must be a non-empty string")


def _require_line(line: str, max_line_chars: int = MAX_LINE_CHARS) -> str:
    if not isinstance(line, str) or not line.strip():
        raise PromptError("thought text is empty")
    if any(unicodedata.category(char) == "Cc" for char in line):
        raise PromptError("thought text contains a control character")
    if len(line) > max_line_chars:
        raise PromptError(f"thought text exceeds {max_line_chars} characters")
    return line


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromptError(f"{label} must be a non-empty string")
    return value


def _escape_quotes(line: str) -> str:
    return line.replace("\\", "\\\\").replace('"', '\\"')
