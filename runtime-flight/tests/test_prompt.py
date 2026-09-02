"""Task 8: deterministic H3 prompt assembly from locked v2 pack fields."""

from __future__ import annotations

import ast
from pathlib import Path
from types import MappingProxyType

import pytest

from runtime_flight.baseline import BaselineContext, CharacterPackTruth, ScenePackTruth
from runtime_flight.prompt import PromptError, assemble_prompt

from conftest import character_manifest_v2, scene_manifest_v2

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

SECRET = "sk-live-secret-should-never-appear"
HERO_PATH = "/secret/local/hero.png"
SOURCE_TEXT = "Over the course of 3 months at OpenAI"
BOT1_VOICE = "Low, measured, dry, warm, with restrained energy."
BOT2_VOICE = "Bright, curious, clipped, with playful lift."
BOT1_NAME = "PHASEONE[lol]"
BOT2_NAME = "deb"
PERSONA = "Calm, dry, optimistic technical anchor."
SOUL = "You would rather be bored than impressed about secret keys."
TTS_PROVIDER = "elevenlabs"
TTS_VOICE = "voice-clone-id-xyz"


def _character(slot: str, *, voice: str, name: str, color: str) -> CharacterPackTruth:
    manifest = character_manifest_v2()
    invariants = dict(manifest["visual_invariants"])
    if slot == "BOT2":
        invariants["silhouette"] = f"Broad rounded {color} software sprite."
        invariants["eye_design"] = "Two solid mint ovals, no pupils or inner marks."
        invariants["proportions"] = "Slightly taller; width is about 1.15 times height."
    manifest = {
        **manifest,
        "visual_invariants": invariants,
        "voice_direction": voice,
        "persona": PERSONA,
        "soul": SOUL,
        "tts": {
            **manifest["tts"],
            "provider": TTS_PROVIDER,
            "voice_id": TTS_VOICE,
        },
        "display_name": name,
    }
    return CharacterPackTruth(
        slot=slot,  # type: ignore[arg-type]
        pack_id=f"char-{slot.lower()}",
        version=2,
        display_name=name,
        manifest=MappingProxyType(manifest),
    )


def _baseline() -> BaselineContext:
    scene = scene_manifest_v2()
    return BaselineContext(
        baseline_id="baseline-secret-id",
        hero_path=Path(HERO_PATH),
        hero_sha256="h" * 64,
        host_map={"BOT1": "host_a", "BOT2": "host_b"},
        display_names={"BOT1": BOT1_NAME, "BOT2": BOT2_NAME},
        reanchor_every=60,
        frame={"w": 1920, "h": 1080, "fps": 30},
        characters=(
            _character("BOT1", voice=BOT1_VOICE, name=BOT1_NAME, color="orange"),
            _character("BOT2", voice=BOT2_VOICE, name=BOT2_NAME, color="mint"),
        ),
        scene=ScenePackTruth(
            pack_id="scene-1",
            version=2,
            manifest=MappingProxyType(scene),
        ),
    )


def test_assemble_prompt_is_exact_v2_export_order():
    line = "Three civilizations rose and fell in three months."
    prompt = assemble_prompt(_baseline(), "BOT1", line)
    expected = (
        "Original flat 2D animated live-show shot.\n"
        "Scene: Warm studio\n"
        "Palette: orange, cream\n"
        "Lighting: Soft key light\n"
        "Camera: locked wide eye-level two-shot, BOT1 left, BOT2 right, no camera movement.\n"
        "BOT1: Broad rounded orange software sprite.; eyes: Two solid cream ovals, no pupils or inner marks.; proportions: Low and wide; width is about 1.35 times height..\n"
        "BOT2: Broad rounded mint software sprite.; eyes: Two solid mint ovals, no pupils or inner marks.; proportions: Slightly taller; width is about 1.15 times height..\n"
        f"Active host voice: {BOT1_VOICE}\n"
        "Action: BOT1 speaks while the other host listens with small eye and body reactions.\n"
        f'Dialogue: "{line}"\n'
        "No readable text, letters, numbers, logos, captions, lower thirds, or UI inside the generated frame."
    )
    assert prompt == expected


def test_prompt_includes_only_active_host_voice_direction_once():
    prompt = assemble_prompt(
        _baseline(),
        "BOT2",
        "The third one took over part of OpenAI.",
    )
    assert prompt.count(BOT2_VOICE) == 1
    assert prompt.count("Active host voice:") == 1
    assert BOT1_VOICE not in prompt
    assert "Active host voice: Bright, curious, clipped, with playful lift." in prompt
    assert "Action: BOT2 speaks while the other host listens" in prompt


def test_prompt_excludes_display_names_persona_tts_source_paths_and_secrets():
    prompt = assemble_prompt(
        _baseline(),
        "BOT1",
        "Three civilizations rose and fell in three months.",
    )
    for leaked in (
        BOT1_NAME,
        BOT2_NAME,
        PERSONA,
        SOUL,
        TTS_PROVIDER,
        TTS_VOICE,
        SOURCE_TEXT,
        HERO_PATH,
        SECRET,
        "baseline-secret-id",
        "host_a",
        "writer_rules",
        "elevenlabs",
    ):
        assert leaked not in prompt


def test_dialogue_quotes_are_escaped():
    prompt = assemble_prompt(_baseline(), "BOT1", 'He said "wiped out" then paused.')
    assert 'Dialogue: "He said \\"wiped out\\" then paused."' in prompt
    assert 'Dialogue: "He said "wiped out" then paused."' not in prompt


def test_empty_line_is_rejected():
    with pytest.raises(PromptError, match="empty"):
        assemble_prompt(_baseline(), "BOT1", "   ")


def test_control_character_line_is_rejected():
    with pytest.raises(PromptError, match="control"):
        assemble_prompt(_baseline(), "BOT1", "hello\x00civilizations")


def test_pathological_line_over_120_characters_is_rejected():
    with pytest.raises(PromptError, match="120"):
        assemble_prompt(_baseline(), "BOT1", "x" * 121)


def test_unknown_speaker_is_rejected():
    with pytest.raises(PromptError, match="speaker"):
        assemble_prompt(_baseline(), "HOST", "A line.")  # type: ignore[arg-type]


def test_prompt_module_does_not_import_root_scaffold_or_fal() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "prompt.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
    assert "fal_client" not in imported
    assert "harness_live" not in imported
