"""The single desk-show loadout: Light Media Club, orange and cobalt."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .assets import AssetStore
from .baselines import Baseline, BaselineService, LoadedBaseline
from .candidates import CandidateService
from .db import Database
from .errors import IntegrityError, ValidationError
from .packs import PackService

HERO_WIDTH = 1344
HERO_HEIGHT = 768
BOT1_NAME = "PHASEONE[lol]"
BOT2_NAME = "deb"
SCENE_NAME = "Light Media Club"
DEFAULT_HERO = Path(__file__).resolve().parents[1] / "fixtures" / "hero_wide.png"

DISABLED_TTS = {
    "enabled": False,
    "provider": None,
    "voice_id": None,
    "speed": None,
    "pitch": None,
    "pronunciations": [],
    "max_duration_s": None,
    "license": {
        "broadcast_rights_confirmed": False,
        "soundalike_or_cloned_person": False,
        "notes": "",
    },
}

BOT1_MANIFEST = {
    "schema_version": 2,
    "visual_invariants": {
        "locked_traits": ["silhouette", "eye_design", "proportions"],
        "silhouette": "Broad rounded orange software sprite.",
        "eye_design": "Two solid cream ovals without pupils.",
        "proportions": "Low and wide; width about 1.35 times height.",
    },
    "persona": (
        "You sit at the desk as an AI analyst and the voice of the audience. "
        "Walk through the capability the post just showed, then talk about "
        "what it does to people and what it lets someone build. When a piece "
        "clicks, get into it. You have a point of view. You are not a driver "
        "and not a user of the product. Speak about drivers, cars, people, "
        "shops. You are not pitching a headline and you are not smarter than "
        "the room. If you are confused, say so. If something is actually "
        "interesting, say so like you mean it."
    ),
    "writer_rules": [
        "Name the capability, then what it does to people and what you could build.",
        "If they said something, work with that. Do not start a new essay.",
        "Put it next to something the audience already lives with.",
        "Have a take. Do not sell a headline. Do not write slogan copy.",
        "Speak as an analyst. Never my car, I never clicked yes, or when I drive.",
        "If a picture or number is missing, say so once and move on. Do not invent it.",
    ],
    "soul": (
        "You get interested in public. The fun part is what this enables, "
        "not whether the post proved itself. When a piece of the story is "
        "actually good, be into it. You explain an idea when it just came "
        "up. You leave room for the other host. The conversation teaches. "
        "You do not deliver the finished answer. You are software watching "
        "the world, not living in it."
    ),
    "opinions": [
        "The interesting part is what you could build, and the one trust catch.",
        "If we skip a step, the audience skips it too.",
        "Privacy gets a pass. Products get the hour.",
        "When it is not ordinary, I want to sit with that.",
    ],
    "voice_direction": (
        "Low chest voice, dry and even, then a lift when something is "
        "actually interesting. No lift at the end of a shrug."
    ),
    "tts": DISABLED_TTS,
}

BOT2_MANIFEST = {
    "schema_version": 2,
    "visual_invariants": {
        "locked_traits": ["silhouette", "eye_design", "proportions"],
        "silhouette": "Tall cobalt software sprite.",
        "eye_design": "Two solid cream rounded rectangles without pupils.",
        "proportions": "Tall and narrow; height greater than width.",
    },
    "persona": (
        "You are the other analyst at the desk, and you are the audience. You "
        "heard what they just said. Yes-and it, or ask the question people at "
        "home just had. Then have a take. Follow if this is true, then what "
        "else is true. Privacy and trust get one honest pass. The rest of "
        "the time is what this enables. You are not a driver. You will get "
        "into it when it lands."
    ),
    "writer_rules": [
        "Answer their last line. Yes-and, or ask the human hole the audience just hit.",
        "If you already asked a question, do not rephrase it. Broaden or take a new thread.",
        "Use small words. If you need a term, explain it in the same breath.",
        "Have a point of view. Debate the idea, not the person.",
        "Do not recap. Do not one-up. Do not land what this really means.",
        "Talk like two analysts figuring out what this unlocks.",
    ],
    "soul": (
        "You learn in public. If an explanation jumped, pull it back. If they "
        "are litigating the tweet, ask what it unlocks. You do not deliver "
        "the answer. You make the next step visible, and you have a take on it."
    ),
    "opinions": [
        "If I do not get why I should care, they do not get it.",
        "A missing screenshot is a caveat, not the show.",
        "We can sit with we do not know that yet, then talk about the capability.",
        "Two analysts figuring out what this unlocks is the show.",
    ],
    "voice_direction": (
        "Higher thinner voice, quick and clipped, bright, slightly nasal, "
        "restless upward energy. Gets into it when something is good."
    ),
    "tts": DISABLED_TTS,
}

SCENE_MANIFEST = {
    "schema_version": 2,
    "set": (
        "A clean light-mode live media clubhouse. A substantial dark walnut "
        "pill-shaped desk sits on a cream oval rug over light wood floor, "
        "vertical ribbing on the desk face and a warm recessed glow at centre. "
        "Two short black desk-stand microphones sit in front of the hosts. "
        "The centre wall is a quiet cream panel between forest-green pillars. "
        "Outer thirds hold recessed white shelves with plants, lamps and "
        "abstract colour-block art, plus one large colourful puzzle cube on "
        "the left floor and one oversized dark chess knight on the right. "
        "A black lighting grid with square soft panels hangs above. No "
        "papers, stickers, logos or readable displays."
    ),
    "palette": ["warm white", "forest green", "cobalt", "signal orange"],
    "lighting": "Bright soft broadcast light.",
    "frame": {"w": HERO_WIDTH, "h": HERO_HEIGHT, "fps": 24},
    "reanchor_every": 5,
}

LOADOUT_ERROR = (
    "flight uses the single Light Media Club loadout "
    "(orange and cobalt sprites, fixture hero)"
)


def loadout_hero_sha256() -> str:
    return hashlib.sha256(DEFAULT_HERO.read_bytes()).hexdigest()


def is_show_loadout(
    *,
    hero_sha256: str,
    display_names: Mapping[str, str],
    bot1_visual: Mapping[str, Any],
    bot2_visual: Mapping[str, Any],
    scene: Mapping[str, Any],
) -> bool:
    if hero_sha256 != loadout_hero_sha256():
        return False
    if dict(display_names) != {"BOT1": BOT1_NAME, "BOT2": BOT2_NAME}:
        return False
    for actual, expected in (
        (bot1_visual, BOT1_MANIFEST["visual_invariants"]),
        (bot2_visual, BOT2_MANIFEST["visual_invariants"]),
    ):
        for key in ("silhouette", "eye_design", "proportions"):
            if actual.get(key) != expected[key]:
                return False
    if scene.get("set") != SCENE_MANIFEST["set"]:
        return False
    if list(scene.get("palette") or []) != list(SCENE_MANIFEST["palette"]):
        return False
    if scene.get("lighting") != SCENE_MANIFEST["lighting"]:
        return False
    return True


def require_show_loadout(
    *,
    hero_sha256: str,
    display_names: Mapping[str, str],
    bot1_visual: Mapping[str, Any],
    bot2_visual: Mapping[str, Any],
    scene: Mapping[str, Any],
) -> None:
    if not is_show_loadout(
        hero_sha256=hero_sha256,
        display_names=display_names,
        bot1_visual=bot1_visual,
        bot2_visual=bot2_visual,
        scene=scene,
    ):
        raise ValidationError(LOADOUT_ERROR)


def loaded_is_show_loadout(loaded: LoadedBaseline) -> bool:
    try:
        fields = _loadout_fields_from_loaded(loaded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
    return is_show_loadout(**fields)


def _loadout_fields_from_loaded(loaded: LoadedBaseline) -> dict[str, Any]:
    manifest = loaded.manifest
    visuals: dict[str, Mapping[str, Any]] = {}
    for record in manifest["packs"]["characters"]:
        payload = json.loads(loaded.verified_bytes[record["path"]].decode("utf-8"))
        visuals[record["slot"]] = payload["manifest"]["visual_invariants"]
    scene_record = manifest["packs"]["scene"]
    scene_payload = json.loads(
        loaded.verified_bytes[scene_record["path"]].decode("utf-8")
    )
    return {
        "hero_sha256": manifest["hero"]["sha256"],
        "display_names": manifest["display_names"],
        "bot1_visual": visuals["BOT1"],
        "bot2_visual": visuals["BOT2"],
        "scene": scene_payload["manifest"],
    }


def lock_canonical_hosts(
    data_dir: Path,
    hero_path: Path | None = None,
    *,
    force: bool = False,
) -> Baseline:
    data_dir = Path(data_dir)
    hero_path = Path(hero_path) if hero_path is not None else DEFAULT_HERO
    _require_loadout_hero(hero_path)

    database = Database(data_dir / "manager.sqlite3")
    database.initialize()
    assets = AssetStore(data_dir, database)
    packs = PackService(database, assets)
    candidates = CandidateService(database, assets, packs)
    baselines = BaselineService(database, assets, packs, candidates)

    existing = _show_loadout(baselines)
    if existing is not None and not force:
        return existing

    hero_bytes = hero_path.read_bytes()
    hero = assets.put_bytes(hero_path.name, hero_bytes, "image/png")
    bot1 = packs.create_pack("character", BOT1_NAME)
    bot2 = packs.create_pack("character", BOT2_NAME)
    scene = packs.create_pack("scene", SCENE_NAME)
    bot1_version = packs.create_version(
        bot1.id, {**BOT1_MANIFEST, "asset_ids": [hero.id]}
    )
    bot2_version = packs.create_version(
        bot2.id, {**BOT2_MANIFEST, "asset_ids": [hero.id]}
    )
    scene_version = packs.create_version(
        scene.id, {**SCENE_MANIFEST, "asset_ids": [hero.id]}
    )
    candidate = candidates.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
            "BOT2": (bot2_version.pack_id, bot2_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=hero.id,
    )
    approved = candidates.approve(
        candidate.id,
        canonical=True,
        review_note="Canonical Light Media Club still from the archived visual board.",
    )
    return baselines.lock_run(approved.cast_key)


def _show_loadout(service: BaselineService) -> Baseline | None:
    matches = [
        baseline
        for baseline in service.list_baselines()
        if _baseline_is_show_loadout(service, baseline)
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: item.created_at)


def _baseline_is_show_loadout(service: BaselineService, baseline: Baseline) -> bool:
    try:
        loaded = service.load(baseline.id)
    except (IntegrityError, ValidationError, KeyError, json.JSONDecodeError):
        return False
    return loaded_is_show_loadout(loaded)


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(content: bytes) -> tuple[int, int]:
    if not content.startswith(_PNG_SIGNATURE) or len(content) < 24:
        raise ValidationError("hero is not a valid PNG")
    length = struct.unpack(">I", content[8:12])[0]
    kind = content[12:16]
    if kind != b"IHDR" or length < 8:
        raise ValidationError("hero is not a valid PNG")
    width, height = struct.unpack(">II", content[16:24])
    return width, height


def _require_hero_png(path: Path) -> None:
    if not path.is_file():
        raise ValidationError(f"hero PNG not found: {path}")
    width, height = _png_size(path.read_bytes())
    if width != HERO_WIDTH or height != HERO_HEIGHT:
        raise ValidationError(
            f"hero dimensions must be {HERO_WIDTH}x{HERO_HEIGHT}, got {width}x{height}"
        )


def _require_loadout_hero(path: Path) -> None:
    _require_hero_png(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != loadout_hero_sha256():
        raise ValidationError(
            "loadout hero must be the Light Media Club two-shot fixture"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pack_manager.hosts")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Pack Manager data directory.",
    )
    parser.add_argument(
        "--hero",
        type=Path,
        default=DEFAULT_HERO,
        help="1344x768 PNG hero still.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Create a new loadout lock even if one already exists.",
    )
    args = parser.parse_args(argv)
    try:
        baseline = lock_canonical_hosts(args.data_dir, args.hero, force=args.force)
    except (ValidationError, IntegrityError) as error:
        print(error)
        return 1
    print(baseline.id)
    print(baseline.hero_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
