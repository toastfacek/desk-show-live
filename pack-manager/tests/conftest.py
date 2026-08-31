import pytest

from pack_manager.assets import AssetStore
from pack_manager.db import Database


def disabled_tts_block():
    return {
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


def character_manifest_v1(asset_ids=()):
    return {
        "visual_invariants": {
            "locked_traits": ["silhouette", "eye_design", "proportions"]
        },
        "persona": "Calm and curious.",
        "writer_rules": ["Prefer evidence."],
        "voice_direction": "Measured and warm.",
        "asset_ids": list(asset_ids),
    }


def character_manifest_v2(asset_ids=()):
    return {
        "schema_version": 2,
        "visual_invariants": {
            "locked_traits": ["silhouette", "eye_design", "proportions"],
            "silhouette": "Broad rounded orange software sprite.",
            "eye_design": "Two solid cream ovals, no pupils or inner marks.",
            "proportions": "Low and wide; width is about 1.35 times height.",
        },
        "persona": "Calm, dry, optimistic technical anchor.",
        "writer_rules": ["Make one clear claim per thought."],
        "voice_direction": "Low, measured, dry, warm, with restrained energy.",
        "tts": disabled_tts_block(),
        "asset_ids": list(asset_ids),
    }


def scene_manifest_v1(asset_ids=()):
    return {
        "set": "Warm studio",
        "palette": ["orange", "cream"],
        "lighting": "Soft key light",
        "frame": {"w": 1920, "h": 1080, "fps": 30},
        "reanchor_every": 60,
        "asset_ids": list(asset_ids),
    }


def scene_manifest_v2(asset_ids=()):
    return {
        "schema_version": 2,
        "set": "Warm studio",
        "palette": ["orange", "cream"],
        "lighting": "Soft key light",
        "frame": {"w": 1920, "h": 1080, "fps": 30},
        "reanchor_every": 60,
        "asset_ids": list(asset_ids),
    }


@pytest.fixture
def asset_store(tmp_path):
    database = Database(tmp_path / "manager.sqlite3")
    database.initialize()
    return AssetStore(tmp_path / "data", database, max_bytes=1024)
