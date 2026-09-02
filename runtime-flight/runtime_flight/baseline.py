from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from PIL import Image

from pack_manager.baselines import LoadedBaseline
from pack_manager.errors import ValidationError
from pack_manager.hosts import require_show_loadout
from pack_manager.runtime import load_locked_baseline

HERO_WIDTH = 1344
HERO_HEIGHT = 768


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class CharacterPackTruth:
    slot: Literal["BOT1", "BOT2"]
    pack_id: str
    version: int
    display_name: str
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class ScenePackTruth:
    pack_id: str
    version: int
    manifest: Mapping[str, Any]


@dataclass(frozen=True)
class BaselineContext:
    baseline_id: str
    hero_path: Path
    hero_sha256: str
    host_map: Mapping[str, str]
    display_names: Mapping[str, str]
    reanchor_every: int
    frame: Mapping[str, Any]
    characters: tuple[CharacterPackTruth, CharacterPackTruth]
    scene: ScenePackTruth

    @classmethod
    def load(cls, data_dir: Path, baseline_id: str) -> BaselineContext:
        loaded = load_locked_baseline(data_dir, baseline_id)
        hero_relative = loaded.manifest["hero"]["path"]
        hero_bytes = loaded.verified_bytes[hero_relative]
        hero_sha256 = loaded.manifest["hero"]["sha256"]
        _validate_hero_png(hero_bytes, hero_sha256)
        return cls._from_loaded(loaded, hero_bytes)

    @classmethod
    def load_loadout(cls, data_dir: Path, baseline_id: str) -> BaselineContext:
        context = cls.load(data_dir, baseline_id)
        bot1 = next(character for character in context.characters if character.slot == "BOT1")
        bot2 = next(character for character in context.characters if character.slot == "BOT2")
        require_show_loadout(
            hero_sha256=context.hero_sha256,
            display_names=context.display_names,
            bot1_visual=bot1.manifest.get("visual_invariants", {}),
            bot2_visual=bot2.manifest.get("visual_invariants", {}),
            scene=context.scene.manifest,
        )
        return context

    @staticmethod
    def _from_loaded(loaded: LoadedBaseline, hero_bytes: bytes) -> BaselineContext:
        manifest = loaded.manifest
        hero_relative = manifest["hero"]["path"]

        characters: list[CharacterPackTruth] = []
        for record in sorted(
            manifest["packs"]["characters"], key=lambda item: item["slot"]
        ):
            payload = json.loads(loaded.verified_bytes[record["path"]].decode("utf-8"))
            characters.append(
                CharacterPackTruth(
                    slot=record["slot"],
                    pack_id=record["pack_id"],
                    version=record["version"],
                    display_name=manifest["display_names"][record["slot"]],
                    manifest=_deep_freeze(payload["manifest"]),
                )
            )

        scene_record = manifest["packs"]["scene"]
        scene_payload = json.loads(
            loaded.verified_bytes[scene_record["path"]].decode("utf-8")
        )
        scene = ScenePackTruth(
            pack_id=scene_record["pack_id"],
            version=scene_record["version"],
            manifest=_deep_freeze(scene_payload["manifest"]),
        )

        return BaselineContext(
            baseline_id=loaded.id,
            hero_path=loaded.hero_path,
            hero_sha256=manifest["hero"]["sha256"],
            host_map=_deep_freeze(manifest["host_map"]),
            display_names=_deep_freeze(manifest["display_names"]),
            reanchor_every=manifest["reanchor_every"],
            frame=_deep_freeze(manifest["frame"]),
            characters=(characters[0], characters[1]),
            scene=scene,
        )


def _validate_hero_png(content: bytes, expected_sha256: str) -> None:
    digest = hashlib.sha256(content).hexdigest()
    if digest != expected_sha256:
        raise ValidationError("hero hash mismatch")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "PNG":
                raise ValidationError(f"hero must be decoded PNG, got {image.format}")
            image.load()
            width, height = image.size
    except ValidationError:
        raise
    except Exception as error:
        raise ValidationError("hero is not a valid PNG") from error
    if width != HERO_WIDTH or height != HERO_HEIGHT:
        raise ValidationError(
            f"hero dimensions must be {HERO_WIDTH}x{HERO_HEIGHT}, got {width}x{height}"
        )
