from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from PIL import Image

from pack_manager.baselines import LoadedBaseline
from pack_manager.errors import ValidationError
from pack_manager.runtime import load_locked_baseline

HERO_WIDTH = 1344
HERO_HEIGHT = 768
_ROOT_SCAFFOLD_HERO = Path("assets/hero.png")
_ROOT_CONFIG_YAML = Path("config.yaml")


@dataclass(frozen=True)
class CharacterPackTruth:
    slot: Literal["BOT1", "BOT2"]
    pack_id: str
    version: int
    display_name: str
    manifest: dict


@dataclass(frozen=True)
class ScenePackTruth:
    pack_id: str
    version: int
    manifest: dict


@dataclass(frozen=True)
class BaselineContext:
    baseline_id: str
    hero_path: Path
    hero_sha256: str
    host_map: dict[str, str]
    display_names: dict[str, str]
    reanchor_every: int
    frame: dict
    characters: tuple[CharacterPackTruth, CharacterPackTruth]
    scene: ScenePackTruth

    @classmethod
    def load(cls, data_dir: Path, baseline_id: str) -> BaselineContext:
        loaded = load_locked_baseline(data_dir, baseline_id)
        hero_sha256 = loaded.manifest["hero"]["sha256"]
        _validate_hero_png(loaded.hero_path, hero_sha256)
        _reject_root_scaffold_hero(loaded.hero_path, hero_sha256)
        return cls._from_loaded(loaded)

    @staticmethod
    def _from_loaded(loaded: LoadedBaseline) -> BaselineContext:
        manifest = loaded.manifest
        export_dir = loaded.manifest_path.parent

        characters: list[CharacterPackTruth] = []
        for record in sorted(
            manifest["packs"]["characters"], key=lambda item: item["slot"]
        ):
            payload = json.loads(
                (export_dir / record["path"]).read_text(encoding="utf-8")
            )
            characters.append(
                CharacterPackTruth(
                    slot=record["slot"],
                    pack_id=record["pack_id"],
                    version=record["version"],
                    display_name=manifest["display_names"][record["slot"]],
                    manifest=payload["manifest"],
                )
            )

        scene_record = manifest["packs"]["scene"]
        scene_payload = json.loads(
            (export_dir / scene_record["path"]).read_text(encoding="utf-8")
        )
        scene = ScenePackTruth(
            pack_id=scene_record["pack_id"],
            version=scene_record["version"],
            manifest=scene_payload["manifest"],
        )

        return BaselineContext(
            baseline_id=loaded.id,
            hero_path=loaded.hero_path,
            hero_sha256=manifest["hero"]["sha256"],
            host_map=dict(manifest["host_map"]),
            display_names=dict(manifest["display_names"]),
            reanchor_every=manifest["reanchor_every"],
            frame=dict(manifest["frame"]),
            characters=(characters[0], characters[1]),
            scene=scene,
        )


def _validate_hero_png(path: Path, expected_sha256: str) -> None:
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValidationError("hero hash mismatch")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "PNG":
                raise ValidationError(f"hero must be decoded PNG, got {image.format}")
            width, height = image.size
    except ValidationError:
        raise
    except Exception as error:
        raise ValidationError("hero is not a valid PNG") from error
    if width != HERO_WIDTH or height != HERO_HEIGHT:
        raise ValidationError(
            f"hero dimensions must be {HERO_WIDTH}x{HERO_HEIGHT}, got {width}x{height}"
        )


def _reject_root_scaffold_hero(hero_path: Path, expected_sha256: str) -> None:
    resolved_hero = hero_path.resolve()
    cwd = Path.cwd()

    scaffold = (cwd / _ROOT_SCAFFOLD_HERO).resolve()
    if scaffold.is_file() and resolved_hero == scaffold:
        raise ValidationError("root scaffold hero path is not flight truth")

    config_path = cwd / _ROOT_CONFIG_YAML
    if not config_path.is_file():
        return

    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValidationError("invalid root config.yaml") from error
    if not isinstance(config, dict):
        return

    identity = config.get("identity")
    if not isinstance(identity, dict):
        return

    hero_still = identity.get("hero_still")
    if not isinstance(hero_still, str) or not hero_still.strip():
        return

    config_hero = (cwd / hero_still).resolve()
    if resolved_hero == config_hero:
        raise ValidationError("config.yaml hero_still path is not flight truth")
    if config_hero.is_file():
        config_hash = hashlib.sha256(config_hero.read_bytes()).hexdigest()
        if config_hash == expected_sha256:
            raise ValidationError(
                "hero matches root config.yaml hero_still; use locked export only"
            )
