import pytest

from pack_manager.assets import AssetStore
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.errors import ConflictError, ValidationError
from pack_manager.packs import PackService


def character_manifest(asset_ids=()):
    return {
        "visual_invariants": {
            "locked_traits": ["silhouette", "eye_design", "proportions"]
        },
        "persona": "Calm and curious.",
        "writer_rules": ["Prefer evidence."],
        "voice_direction": "Measured and warm.",
        "asset_ids": list(asset_ids),
    }


def scene_manifest(asset_ids=()):
    return {
        "set": "Warm studio",
        "palette": ["orange", "cream"],
        "lighting": "Soft key light",
        "frame": {"w": 1920, "h": 1080, "fps": 30},
        "reanchor_every": 60,
        "asset_ids": list(asset_ids),
    }


@pytest.fixture
def candidate_setup(tmp_path):
    database = Database(tmp_path / "manager.sqlite3")
    database.initialize()
    asset_store = AssetStore(tmp_path / "data", database)
    pack_service = PackService(database, asset_store)
    candidate_service = CandidateService(database, asset_store, pack_service)

    hero = asset_store.put_bytes("hero.png", b"hero", "image/png")
    bot1 = pack_service.create_pack("character", "BOT1")
    bot2 = pack_service.create_pack("character", "BOT2")
    scene = pack_service.create_pack("scene", "Studio")
    bot1_version = pack_service.create_version(bot1.id, character_manifest())
    bot2_version = pack_service.create_version(bot2.id, character_manifest())
    scene_version = pack_service.create_version(scene.id, scene_manifest())

    return {
        "database": database,
        "asset_store": asset_store,
        "pack_service": pack_service,
        "candidate_service": candidate_service,
        "hero": hero,
        "bot1": bot1_version,
        "bot2": bot2_version,
        "scene": scene_version,
    }


@pytest.fixture
def candidate_service(candidate_setup):
    return candidate_setup["candidate_service"]


@pytest.fixture
def canonical_candidate(candidate_setup):
    return candidate_setup["candidate_service"].create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )


@pytest.fixture
def approved_canonical(candidate_service, canonical_candidate):
    return candidate_service.approve(
        canonical_candidate.id, canonical=True, review_note="M0 passed"
    )


@pytest.fixture
def draft_variant(candidate_service, approved_canonical):
    return candidate_service.create_variant(
        canonical_candidate_id=approved_canonical.id,
        hero_asset_id=approved_canonical.hero_asset_id,
        theme="Christmas",
        changes={"palette": ["red", "green"], "accessories": ["Santa hat"]},
    )


def test_only_draft_candidate_can_be_approved(
    candidate_service, canonical_candidate
):
    approved = candidate_service.approve(
        canonical_candidate.id, canonical=True, review_note="M0 passed"
    )

    with pytest.raises(ConflictError, match="draft"):
        candidate_service.reject(approved.id, review_note="changed mind")


def test_rejection_does_not_replace_canonical(
    candidate_service, approved_canonical, draft_variant
):
    candidate_service.reject(draft_variant.id, review_note="wrong palette")

    resolution = candidate_service.resolve(approved_canonical.cast_key)

    assert resolution.candidate.id == approved_canonical.id


def test_unapproved_requested_variant_falls_back(
    candidate_service, approved_canonical, draft_variant
):
    resolution = candidate_service.resolve(
        approved_canonical.cast_key, requested_candidate_id=draft_variant.id
    )

    assert resolution.candidate.id == approved_canonical.id
    assert resolution.fallback_reason == "requested candidate is not approved"


@pytest.mark.parametrize("trait", ["silhouette", "eye_design", "proportions"])
def test_variant_cannot_override_locked_character_trait(
    candidate_service, approved_canonical, trait
):
    with pytest.raises(ValidationError, match=trait):
        candidate_service.create_variant(
            canonical_candidate_id=approved_canonical.id,
            hero_asset_id=approved_canonical.hero_asset_id,
            theme="Christmas",
            changes={"characters": {"BOT1": {trait: "different"}}},
        )


def test_cast_key_preserves_character_slot_order(candidate_setup):
    service = candidate_setup["candidate_service"]
    common = {
        "scene_pack_id": candidate_setup["scene"].pack_id,
        "scene_version": 1,
        "hero_asset_id": candidate_setup["hero"].id,
    }
    first = service.create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        **common,
    )
    swapped = service.create(
        character_versions={
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
        },
        **common,
    )

    assert first.cast_key != swapped.cast_key


def test_approved_variant_resolves_without_fallback(
    candidate_service, approved_canonical, draft_variant
):
    approved_variant = candidate_service.approve(
        draft_variant.id, canonical=False, review_note="Theme passed"
    )

    resolution = candidate_service.resolve(
        approved_canonical.cast_key,
        requested_candidate_id=approved_variant.id,
    )

    assert resolution.candidate == approved_variant
    assert resolution.fallback_reason is None


def test_variant_inherits_canonical_lineage(
    candidate_service, approved_canonical, draft_variant
):
    assert draft_variant.canonical_candidate_id == approved_canonical.id
    assert draft_variant.cast_key == approved_canonical.cast_key
    assert draft_variant.character_versions == approved_canonical.character_versions
    assert draft_variant.scene_pack_id == approved_canonical.scene_pack_id
    assert draft_variant.scene_version == approved_canonical.scene_version


@pytest.mark.parametrize("changes", [{"characters": {}}, {"lighting": "dark"}])
def test_variant_rejects_changes_outside_allowlist(
    candidate_service, approved_canonical, changes
):
    with pytest.raises(ValidationError, match="changes"):
        candidate_service.create_variant(
            canonical_candidate_id=approved_canonical.id,
            hero_asset_id=approved_canonical.hero_asset_id,
            theme="Christmas",
            changes=changes,
        )


def test_candidate_requires_existing_versions_and_hero(candidate_setup):
    service = candidate_setup["candidate_service"]
    with pytest.raises(ValidationError, match="character version"):
        service.create(
            character_versions={"BOT1": ("missing", 1)},
            scene_pack_id=candidate_setup["scene"].pack_id,
            scene_version=1,
            hero_asset_id=candidate_setup["hero"].id,
        )

    with pytest.raises(ValidationError, match="hero"):
        service.create(
            character_versions={
                "BOT1": (candidate_setup["bot1"].pack_id, 1)
            },
            scene_pack_id=candidate_setup["scene"].pack_id,
            scene_version=1,
            hero_asset_id="asset_missing",
        )


def test_canonical_replacement_is_explicit(candidate_setup, approved_canonical):
    service = candidate_setup["candidate_service"]
    replacement = service.create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )
    approved_replacement = service.approve(
        replacement.id, canonical=True, review_note="New M0 passed"
    )

    assert service.resolve(replacement.cast_key).candidate == approved_replacement
    assert approved_canonical.status == "approved"
