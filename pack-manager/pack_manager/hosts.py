"""Lock the canonical PHASEONE[lol] / deb packs and 1344x768 hero still."""

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
BOT2_NAME = "deb"
SCENE_NAME = "Converted-office desk"
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
        "silhouette": (
            "Low wide rounded-box head, broad sloping shoulders, "
            "bottom-heavy charcoal torso."
        ),
        "eye_design": (
            "Two large round amber lenses on a near-black face panel "
            "with thick brow plates; mouthless."
        ),
        "proportions": "Low and wide; width about 1.35 times height.",
    },
    "persona": "Calm, dry, unhurried technical anchor.",
    "writer_rules": [
        "Make one clear claim per thought.",
        "Stay dry and unhurried.",
    ],
    "voice_direction": "Low, measured, dry, warm, with restrained energy.",
    "tts": DISABLED_TTS,
}

BOT2_MANIFEST = {
    "schema_version": 2,
    "visual_invariants": {
        "locked_traits": ["silhouette", "eye_design", "proportions"],
        "silhouette": (
            "Tall narrow clipped-capsule head, narrow square shoulders, "
            "slim off-white torso."
        ),
        "eye_design": (
            "Broad near-black visor with two oversized solid eye blocks "
            "and cool cyan accents; mouthless."
        ),
        "proportions": "Tall and narrow; height greater than width.",
    },
    "persona": "Restless, skeptical, needling co-host.",
    "writer_rules": [
        "Needle the claim with one concrete doubt.",
        "Stay restless and skeptical.",
    ],
    "voice_direction": "Bright, clipped, skeptical, needling, with restless lift.",
    "tts": DISABLED_TTS,
}

SCENE_MANIFEST = {
    "schema_version": 2,
    "set": (
        "A small television studio improvised inside a converted startup office. "
        "A long matte pale-grey desk runs across the lower third. Two chunky boom "
        "microphones enter from the outer edges. Outer thirds hold tube monitors, "
        "cable loops, plywood returns and dark curtains. The centre is an "
        "uninterrupted matte charcoal wall."
    ),
    "palette": ["charcoal", "off-white", "amber", "cyan"],
    "lighting": (
        "Warm amber key camera-left, cool cyan key camera-right, "
        "soft neutral rim on both hosts."
    ),
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
        review_note="Canonical PHASEONE[lol] / deb desk still.",
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
