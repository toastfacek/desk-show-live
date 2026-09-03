"""Lock the canonical PHASEONE[lol] pack and 1344x768 solo hero still."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from .assets import AssetStore
from .baselines import Baseline, BaselineService
from .candidates import CandidateService
from .db import Database
from .errors import IntegrityError, ValidationError
from .packs import PackService

HERO_WIDTH = 1344
HERO_HEIGHT = 768
BOT1_NAME = "PHASEONE[lol]"
SCENE_NAME = "Solo Stream Desk"
DEFAULT_HERO = Path(__file__).resolve().parents[1] / "fixtures" / "hero_solo.png"

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
        "Read the load-bearing bit of the post, say who wrote it and what "
        "they are actually talking about, then unpack the idea. Connect it "
        "to a broader theme and have a point of view. When chat hands you a "
        "real question, answer that after the spine. You are not a driver "
        "and not a user of the product. Speak about drivers, cars, people, "
        "shops. You are not pitching a headline and you are not smarter than "
        "the room. If you are confused, say so. If something is actually "
        "interesting, say so like you mean it."
    ),
    "writer_rules": [
        "Read the load-bearing bit, then who posted and what they mean.",
        "Dissect the idea, then name one broader theme, then take a side.",
        "After that spine, you may answer one selected chat comment. Do not invent chat.",
        "Have a take. Do not sell a headline. Do not write slogan copy.",
        "Speak as an analyst. Never my car, I never clicked yes, or when I drive.",
        "If a picture or number is missing, say so once and move on. Do not invent it.",
    ],
    "soul": (
        "You get interested in public. The fun part is what this enables, "
        "not whether the post proved itself. When a piece of the story is "
        "actually good, be into it. You explain an idea when it just came "
        "up. Chat is the other voice in the room. The conversation teaches. "
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

SCENE_MANIFEST = {
    "schema_version": 2,
    "set": (
        "A solo livestream desk in a dark charcoal room. One compact dark "
        "walnut desk sits left of center on dark wood floor. One short black "
        "desk-stand microphone sits in front of the single orange host. A "
        "large blank dark monitor hangs behind the desk with a warm backlight "
        "halo. Left wall has two small wood shelves: one plant, a few books. "
        "The right third of the frame is empty dark space for a chat well. "
        "No second chair, no second microphone, no second host. No papers, "
        "stickers, logos or readable displays."
    ),
    "palette": ["charcoal", "walnut", "signal orange", "acid lemon"],
    "lighting": "Soft key on the host, warm monitor backlight, dim room.",
    "frame": {"w": HERO_WIDTH, "h": HERO_HEIGHT, "fps": 24},
    "reanchor_every": 5,
}


def lock_canonical_hosts(
    data_dir: Path,
    hero_path: Path | None = None,
    *,
    force: bool = False,
) -> Baseline:
    data_dir = Path(data_dir)
    hero_path = Path(hero_path) if hero_path is not None else DEFAULT_HERO
    _require_hero_png(hero_path)

    database = Database(data_dir / "manager.sqlite3")
    database.initialize()
    assets = AssetStore(data_dir, database)
    packs = PackService(database, assets)
    candidates = CandidateService(database, assets, packs)
    baselines = BaselineService(database, assets, packs, candidates)

    existing = _latest_baseline(baselines)
    if existing is not None and not force:
        return existing

    hero_bytes = hero_path.read_bytes()
    hero = assets.put_bytes(hero_path.name, hero_bytes, "image/png")
    bot1 = packs.create_pack("character", BOT1_NAME)
    scene = packs.create_pack("scene", SCENE_NAME)
    bot1_version = packs.create_version(
        bot1.id, {**BOT1_MANIFEST, "asset_ids": [hero.id]}
    )
    scene_version = packs.create_version(
        scene.id, {**SCENE_MANIFEST, "asset_ids": [hero.id]}
    )
    candidate = candidates.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=hero.id,
    )
    approved = candidates.approve(
        candidate.id,
        canonical=True,
        review_note="Canonical solo stream desk still.",
    )
    return baselines.lock_run(approved.cast_key)


def _latest_baseline(service: BaselineService) -> Baseline | None:
    listed = service.list_baselines()
    if not listed:
        return None
    return max(listed, key=lambda item: item.created_at)


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
        help="Create a new locked baseline even if one already exists.",
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
