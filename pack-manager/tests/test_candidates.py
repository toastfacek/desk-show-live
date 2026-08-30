import threading
from concurrent.futures import ThreadPoolExecutor

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
        draft_variant.id,
        canonical=False,
        review_note="Theme passed",
        invariants_verified=True,
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


@pytest.mark.parametrize("changes", [{"characters": {}}, {"lighting": "dark"}, {"set": "dark"}])
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


@pytest.mark.parametrize("trait", ["silhouette", "eye_design", "proportions"])
def test_variant_recursively_rejects_locked_trait_keys(
    candidate_service, approved_canonical, trait
):
    with pytest.raises(ValidationError, match=trait):
        candidate_service.create_variant(
            canonical_candidate_id=approved_canonical.id,
            hero_asset_id=approved_canonical.hero_asset_id,
            theme="Nested bypass",
            changes={"scene": {"nested": [{"metadata": {trait: "different"}}]}},
        )


def test_variant_can_use_alternate_scene_without_changing_cast_lineage(
    candidate_setup, approved_canonical
):
    service = candidate_setup["candidate_service"]
    alternate = candidate_setup["pack_service"].create_pack("scene", "Snow set")
    alternate_version = candidate_setup["pack_service"].create_version(
        alternate.id, scene_manifest()
    )

    variant = service.create_variant(
        canonical_candidate_id=approved_canonical.id,
        hero_asset_id=approved_canonical.hero_asset_id,
        theme="Snow",
        changes={"scene": {"weather": "snow"}},
        scene_pack_id=alternate.id,
        scene_version=alternate_version.version,
    )

    assert (variant.scene_pack_id, variant.scene_version) == (alternate.id, 1)
    assert variant.cast_key == approved_canonical.cast_key
    assert variant.canonical_candidate_id == approved_canonical.id


def test_variant_rejects_non_scene_alternate_version(
    candidate_setup, approved_canonical
):
    with pytest.raises(ValidationError, match="not a scene"):
        candidate_setup["candidate_service"].create_variant(
            canonical_candidate_id=approved_canonical.id,
            hero_asset_id=approved_canonical.hero_asset_id,
            theme="Bad scene",
            changes={"scene": {}},
            scene_pack_id=candidate_setup["bot1"].pack_id,
            scene_version=1,
        )


def test_variant_approval_requires_explicit_invariant_verification(
    candidate_service, draft_variant
):
    with pytest.raises(ValidationError, match="invariants_verified"):
        candidate_service.approve(
            draft_variant.id, canonical=False, review_note="Looks good"
        )


def test_variant_approval_revalidates_stored_changes(
    candidate_setup, draft_variant
):
    with candidate_setup["database"].connect() as connection:
        connection.execute(
            "UPDATE candidates SET changes = ? WHERE id = ?",
            ('{"scene":{"silhouette":"bypass"}}', draft_variant.id),
        )

    with pytest.raises(ValidationError, match="silhouette"):
        candidate_setup["candidate_service"].approve(
            draft_variant.id,
            canonical=False,
            review_note="Looks good",
            invariants_verified=True,
        )


def test_stale_variant_cannot_be_approved_after_canonical_replacement(
    candidate_setup, approved_canonical, draft_variant
):
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
    service.approve(replacement.id, canonical=True, review_note="replacement")

    with pytest.raises(ConflictError, match="stale"):
        service.approve(
            draft_variant.id,
            canonical=False,
            review_note="late approval",
            invariants_verified=True,
        )


def test_concurrent_variant_approval_and_canonical_replacement_are_serialized(
    candidate_setup, approved_canonical, draft_variant
):
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
    gate = threading.Barrier(2)

    def approve_variant():
        gate.wait()
        try:
            return service.approve(
                draft_variant.id,
                canonical=False,
                review_note="concurrent variant",
                invariants_verified=True,
            )
        except ConflictError as error:
            return error

    def replace_canonical():
        gate.wait()
        return service.approve(
            replacement.id,
            canonical=True,
            review_note="concurrent replacement",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        variant_result = executor.submit(approve_variant)
        replacement_result = executor.submit(replace_canonical)
        replacement_result.result()
        result = variant_result.result()

    assert service.resolve(replacement.cast_key).candidate.id == replacement.id
    if isinstance(result, ConflictError):
        assert "stale" in str(result)
        assert service.get(draft_variant.id).status == "draft"
    else:
        assert result.status == "approved"


def test_approved_root_can_be_made_canonical_later(
    candidate_setup, approved_canonical
):
    service = candidate_setup["candidate_service"]
    root = service.create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )
    approved = service.approve(root.id, canonical=False, review_note="approved")

    selected = service.set_canonical(approved.id)

    assert selected == approved
    assert service.resolve(approved.cast_key).candidate == approved


def test_set_canonical_rejects_variant_and_nonapproved_root(
    candidate_setup, candidate_service, approved_canonical, draft_variant
):
    draft_root = candidate_service.create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )
    with pytest.raises(ConflictError, match="approved root"):
        candidate_service.set_canonical(draft_root.id)
    approved_variant = candidate_service.approve(
        draft_variant.id,
        canonical=False,
        review_note="verified",
        invariants_verified=True,
    )
    with pytest.raises(ConflictError, match="approved root"):
        candidate_service.set_canonical(approved_variant.id)


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


def test_variant_rejects_approved_root_that_was_never_canonical(
    candidate_setup, approved_canonical
):
    service = candidate_setup["candidate_service"]
    never_canonical = service.create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )
    approved = service.approve(
        never_canonical.id, canonical=False, review_note="Approved alternative"
    )

    with pytest.raises(ValidationError, match="current canonical"):
        service.create_variant(
            canonical_candidate_id=approved.id,
            hero_asset_id=approved.hero_asset_id,
            theme="Christmas",
            changes={"palette": ["red", "green"]},
        )

    assert service.resolve(approved_canonical.cast_key).candidate == approved_canonical


def test_variant_rejects_superseded_canonical_root(
    candidate_setup, approved_canonical
):
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
    service.approve(
        replacement.id, canonical=True, review_note="Replacement passed"
    )

    with pytest.raises(ValidationError, match="current canonical"):
        service.create_variant(
            canonical_candidate_id=approved_canonical.id,
            hero_asset_id=approved_canonical.hero_asset_id,
            theme="Christmas",
            changes={"palette": ["red", "green"]},
        )


def test_missing_requested_candidate_falls_back(
    candidate_service, approved_canonical
):
    resolution = candidate_service.resolve(
        approved_canonical.cast_key,
        requested_candidate_id="candidate_missing",
    )

    assert resolution.candidate == approved_canonical
    assert resolution.fallback_reason == "requested candidate does not exist"


def test_wrong_cast_requested_candidate_falls_back(
    candidate_setup, approved_canonical
):
    service = candidate_setup["candidate_service"]
    other_root = service.create(
        character_versions={
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )
    other_canonical = service.approve(
        other_root.id, canonical=True, review_note="Other cast passed"
    )
    other_variant = service.create_variant(
        canonical_candidate_id=other_canonical.id,
        hero_asset_id=other_canonical.hero_asset_id,
        theme="Christmas",
        changes={"palette": ["red", "green"]},
    )
    approved_other_variant = service.approve(
        other_variant.id,
        canonical=False,
        review_note="Other theme passed",
        invariants_verified=True,
    )

    resolution = service.resolve(
        approved_canonical.cast_key,
        requested_candidate_id=approved_other_variant.id,
    )

    assert resolution.candidate == approved_canonical
    assert resolution.fallback_reason == "requested candidate has different cast key"


def test_invalid_requested_selection_falls_back(
    candidate_setup, approved_canonical
):
    service = candidate_setup["candidate_service"]
    unrelated_root = service.create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )
    approved_unrelated = service.approve(
        unrelated_root.id,
        canonical=False,
        review_note="Approved but not canonical",
    )

    resolution = service.resolve(
        approved_canonical.cast_key,
        requested_candidate_id=approved_unrelated.id,
    )

    assert resolution.candidate == approved_canonical
    assert (
        resolution.fallback_reason
        == "requested candidate is not a variant of canonical"
    )


@pytest.mark.parametrize("initial_status", ["approved", "rejected"])
@pytest.mark.parametrize("operation", ["approve", "reject"])
def test_non_draft_candidate_rejects_every_transition(
    candidate_setup, initial_status, operation
):
    service = candidate_setup["candidate_service"]
    candidate = service.create(
        character_versions={
            "BOT1": (candidate_setup["bot1"].pack_id, 1),
            "BOT2": (candidate_setup["bot2"].pack_id, 1),
        },
        scene_pack_id=candidate_setup["scene"].pack_id,
        scene_version=1,
        hero_asset_id=candidate_setup["hero"].id,
    )
    if initial_status == "approved":
        candidate = service.approve(
            candidate.id, canonical=False, review_note="Approved"
        )
    else:
        candidate = service.reject(candidate.id, review_note="Rejected")

    with pytest.raises(ConflictError, match="draft"):
        if operation == "approve":
            service.approve(
                candidate.id, canonical=False, review_note="Try again"
            )
        else:
            service.reject(candidate.id, review_note="Try again")
