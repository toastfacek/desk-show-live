import json

from fastapi.testclient import TestClient

from pack_manager.app import create_app


PNG = b"\x89PNG\r\n\x1a\napi-test"


def character_manifest(asset_id):
    return {
        "visual_invariants": {
            "locked_traits": ["silhouette", "eye_design", "proportions"]
        },
        "persona": "Calm and curious.",
        "writer_rules": ["Prefer evidence."],
        "voice_direction": "Measured and warm.",
        "asset_ids": [asset_id],
    }


def scene_manifest(asset_id):
    return {
        "set": "Warm studio",
        "palette": ["orange", "cream"],
        "lighting": "Soft key light",
        "frame": {"w": 1920, "h": 1080, "fps": 30},
        "reanchor_every": 60,
        "asset_ids": [asset_id],
    }


def upload(client, name, content=PNG, mime_type="image/png"):
    response = client.post(
        "/api/assets",
        files={"file": (name, content, mime_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_complete_fallback_workflow(tmp_path):
    with TestClient(create_app(tmp_path / "data", max_upload_bytes=1024)) as client:
        packs = [
            client.post("/api/packs", json={"kind": "character", "name": "BOT1"}),
            client.post("/api/packs", json={"kind": "character", "name": "BOT2"}),
            client.post("/api/packs", json={"kind": "scene", "name": "Studio"}),
        ]
        assert [response.status_code for response in packs] == [201, 201, 201]
        bot1, bot2, scene = [response.json() for response in packs]

        bot1_asset = upload(client, "bot1.png")
        bot2_asset = upload(client, "../../bot2.png", PNG + b"2")
        scene_asset = upload(client, "scene.png", PNG + b"scene")
        hero = upload(client, "hero.png", PNG + b"hero")
        variant_hero = upload(client, "variant.png", PNG + b"variant")

        versions = [
            client.post(
                f"/api/packs/{bot1['id']}/versions",
                json={"manifest": character_manifest(bot1_asset["id"])},
            ),
            client.post(
                f"/api/packs/{bot2['id']}/versions",
                json={"manifest": character_manifest(bot2_asset["id"])},
            ),
            client.post(
                f"/api/packs/{scene['id']}/versions",
                json={"manifest": scene_manifest(scene_asset["id"])},
            ),
        ]
        assert [response.status_code for response in versions] == [201, 201, 201]

        candidate_response = client.post(
            "/api/candidates",
            json={
                "character_versions": {
                    "BOT1": [bot1["id"], 1],
                    "BOT2": [bot2["id"], 1],
                },
                "scene_pack_id": scene["id"],
                "scene_version": 1,
                "hero_asset_id": hero["id"],
            },
        )
        assert candidate_response.status_code == 201
        candidate = candidate_response.json()

        approved_response = client.post(
            f"/api/candidates/{candidate['id']}/approve",
            json={"canonical": True, "review_note": "M0 passed"},
        )
        assert approved_response.status_code == 200
        canonical = approved_response.json()
        assert canonical["status"] == "approved"

        variant_response = client.post(
            "/api/candidates/variants",
            json={
                "canonical_candidate_id": canonical["id"],
                "hero_asset_id": variant_hero["id"],
                "theme": "Christmas",
                "changes": {
                    "palette": ["red", "green"],
                    "accessories": ["Santa hat"],
                },
            },
        )
        assert variant_response.status_code == 201
        variant = variant_response.json()

        baseline_response = client.post(
            "/api/baselines",
            json={
                "cast_key": canonical["cast_key"],
                "requested_candidate_id": variant["id"],
            },
        )
        assert baseline_response.status_code == 201
        baseline = baseline_response.json()
        assert "manifest_path" not in baseline

        manifest_response = client.get(
            f"/api/baselines/{baseline['id']}/manifest"
        )
        assert manifest_response.status_code == 200
        manifest = manifest_response.json()
        assert manifest["candidate_id"] == canonical["id"]
        assert manifest["fallback_reason"] == "requested candidate is not approved"

        verify_response = client.get(f"/api/baselines/{baseline['id']}")
        assert verify_response.status_code == 200
        assert verify_response.json()["verified"] is True
        download = client.get(f"/api/baselines/{baseline['id']}/download/manifest")
        assert download.status_code == 200
        assert json.loads(download.content) == manifest


def test_upload_validation_and_stable_errors(tmp_path):
    with TestClient(create_app(tmp_path / "data", max_upload_bytes=16)) as client:
        unsupported = client.post(
            "/api/assets", files={"file": ("payload.txt", b"x", "text/plain")}
        )
        assert unsupported.status_code == 422
        assert unsupported.json() == {
            "error": {
                "code": "validation_error",
                "message": "unsupported image type: text/plain",
            }
        }

        oversized = client.post(
            "/api/assets",
            files={"file": ("huge.png", b"x" * 17, "image/png")},
        )
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "upload_too_large"

        missing = client.get("/api/candidates/candidate_missing")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"


def test_conflicts_and_locked_mutation(tmp_path):
    with TestClient(create_app(tmp_path / "data")) as client:
        hero = upload(client, "hero.png")
        character_asset = upload(client, "character.png", PNG + b"character")
        scene_asset = upload(client, "scene.png", PNG + b"scene")
        character = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT1"}
        ).json()
        scene = client.post(
            "/api/packs", json={"kind": "scene", "name": "Studio"}
        ).json()
        client.post(
            f"/api/packs/{character['id']}/versions",
            json={"manifest": character_manifest(character_asset["id"])},
        )
        client.post(
            f"/api/packs/{scene['id']}/versions",
            json={"manifest": scene_manifest(scene_asset["id"])},
        )
        candidate = client.post(
            "/api/candidates",
            json={
                "character_versions": {"BOT1": [character["id"], 1]},
                "scene_pack_id": scene["id"],
                "scene_version": 1,
                "hero_asset_id": hero["id"],
            },
        ).json()
        client.post(
            f"/api/candidates/{candidate['id']}/approve",
            json={"canonical": True, "review_note": "approved"},
        )

        illegal = client.post(
            f"/api/candidates/{candidate['id']}/reject",
            json={"review_note": "changed mind"},
        )
        assert illegal.status_code == 409
        assert illegal.json() == {
            "error": {"code": "conflict", "message": "candidate is not draft"}
        }

        baseline = client.post(
            "/api/baselines", json={"cast_key": candidate["cast_key"]}
        ).json()
        locked = client.delete(f"/api/baselines/{baseline['id']}")
        assert locked.status_code == 409
        assert locked.json()["error"]["code"] == "conflict"
