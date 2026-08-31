import json

from fastapi.testclient import TestClient

from pack_manager.app import create_app


PNG = b"\x89PNG\r\n\x1a\napi-test"
MUTATION_HEADERS = {"X-Runtime-Manager": "1"}


def manager_client(app):
    return TestClient(
        app, base_url="http://localhost", headers=MUTATION_HEADERS
    )


from conftest import character_manifest_v2, scene_manifest_v2


def character_manifest(asset_id):
    manifest = character_manifest_v2([asset_id])
    return manifest


def scene_manifest(asset_id):
    return scene_manifest_v2([asset_id])


def upload(client, name, content=PNG, mime_type="image/png"):
    response = client.post(
        "/api/assets",
        files={"file": (name, content, mime_type)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_complete_fallback_workflow(tmp_path):
    with manager_client(create_app(tmp_path / "data", max_upload_bytes=1024)) as client:
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
                    "accessories": {"BOT1": ["Santa hat"]},
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
    with manager_client(
        create_app(tmp_path / "data", max_upload_bytes=16, max_request_bytes=256)
    ) as client:
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


def test_request_limiter_rejects_content_length_and_streaming_bodies(tmp_path):
    app = create_app(
        tmp_path / "data", max_upload_bytes=16, max_request_bytes=64
    )
    with manager_client(app) as client:
        declared = client.post(
            "/api/packs",
            content=b"x" * 65,
            headers={"content-type": "application/json"},
        )
        streamed = client.post(
            "/api/packs",
            content=(chunk for chunk in (b"x" * 40, b"y" * 40)),
            headers={
                "content-type": "application/json",
                "transfer-encoding": "chunked",
            },
        )

    for response in (declared, streamed):
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"


def test_localhost_host_header_and_mutation_hardening(tmp_path):
    app = create_app(tmp_path / "data")
    with TestClient(app, base_url="http://localhost") as client:
        readable = client.get("/api/packs")
        missing_marker = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT1"}
        )
        hostile_host = client.get(
            "/api/packs", headers={"host": "attacker.example"}
        )
        hostile_origin = client.post(
            "/api/packs",
            json={"kind": "character", "name": "BOT1"},
            headers={
                **MUTATION_HEADERS,
                "origin": "https://attacker.example",
            },
        )
        accepted = client.post(
            "/api/packs",
            json={"kind": "character", "name": "BOT1"},
            headers=MUTATION_HEADERS,
        )

    assert readable.status_code == 200
    assert accepted.status_code == 201
    for response in (missing_marker, hostile_host, hostile_origin):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "unsafe_request"


def test_api_rejects_blank_pack_names_and_normalizes_surrounding_space(tmp_path):
    with manager_client(create_app(tmp_path / "data")) as client:
        blank = client.post(
            "/api/packs", json={"kind": "character", "name": "   "}
        )
        normalized = client.post(
            "/api/packs",
            json={"kind": "character", "name": "  PHASEONE[lol] Host  "},
        )
        listed = client.get("/api/packs").json()

    assert blank.status_code == 422
    assert blank.json()["error"]["code"] in {
        "request_validation",
        "validation_error",
    }
    assert normalized.status_code == 201
    assert normalized.json()["name"] == "PHASEONE[lol] Host"
    assert [pack["name"] for pack in listed] == ["PHASEONE[lol] Host"]


def test_asset_content_is_verified_and_available_for_previews(tmp_path):
    app = create_app(tmp_path / "data")
    with manager_client(app) as client:
        asset = upload(client, "preview.png")

        content = client.get(f"/api/assets/{asset['id']}/content")

        assert content.status_code == 200
        assert content.headers["content-type"] == "image/png"
        assert content.content == PNG
        app.state.services.assets.get(asset["id"]).path.write_bytes(b"tampered")
        tampered = client.get(f"/api/assets/{asset['id']}/content")
        assert tampered.status_code == 409
        assert tampered.json()["error"]["code"] == "integrity_error"


def test_rejects_image_mime_with_forged_file_signature(tmp_path):
    with manager_client(create_app(tmp_path / "data")) as client:
        forged = client.post(
            "/api/assets",
            files={"file": ("forged.png", b"not a png", "image/png")},
        )

        assert forged.status_code == 422
        assert forged.json() == {
            "error": {
                "code": "validation_error",
                "message": "file signature does not match image/png",
            }
        }


def test_all_request_and_routing_failures_have_stable_envelopes(tmp_path):
    with manager_client(create_app(tmp_path / "data")) as client:
        cases = [
            (
                client.post("/api/packs", json={"kind": "character"}),
                422,
                "request_validation",
            ),
            (
                client.post(
                    "/api/packs",
                    content=b"{",
                    headers={"content-type": "application/json"},
                ),
                400,
                "malformed_request",
            ),
            (
                client.post(
                    "/api/assets",
                    content=b"broken multipart",
                    headers={"content-type": "multipart/form-data"},
                ),
                400,
                "malformed_request",
            ),
            (client.get("/api/does-not-exist"), 404, "not_found"),
            (client.put("/api/packs"), 405, "method_not_allowed"),
        ]

        for response, status, code in cases:
            assert response.status_code == status
            assert response.json()["error"]["code"] == code
            assert isinstance(response.json()["error"]["message"], str)
            assert set(response.json()) == {"error"}


def test_conflicts_and_locked_mutation(tmp_path):
    with manager_client(create_app(tmp_path / "data")) as client:
        hero = upload(client, "hero.png")
        character_asset = upload(client, "character.png", PNG + b"character")
        scene_asset = upload(client, "scene.png", PNG + b"scene")
        character = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT1"}
        ).json()
        character2 = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT2"}
        ).json()
        scene = client.post(
            "/api/packs", json={"kind": "scene", "name": "Studio"}
        ).json()
        client.post(
            f"/api/packs/{character['id']}/versions",
            json={"manifest": character_manifest(character_asset["id"])},
        )
        client.post(
            f"/api/packs/{character2['id']}/versions",
            json={"manifest": character_manifest(character_asset["id"])},
        )
        client.post(
            f"/api/packs/{scene['id']}/versions",
            json={"manifest": scene_manifest(scene_asset["id"])},
        )
        candidate = client.post(
            "/api/candidates",
            json={
                "character_versions": {
                    "BOT1": [character["id"], 1],
                    "BOT2": [character2["id"], 1],
                },
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


def test_verified_manifest_download_rechecks_in_memory_bytes(tmp_path):
    app = create_app(tmp_path / "data")
    with manager_client(app) as client:
        hero = upload(client, "hero.png")
        character = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT1"}
        ).json()
        character2 = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT2"}
        ).json()
        scene = client.post(
            "/api/packs", json={"kind": "scene", "name": "Studio"}
        ).json()
        client.post(
            f"/api/packs/{character['id']}/versions",
            json={"manifest": character_manifest(hero["id"])},
        )
        client.post(
            f"/api/packs/{character2['id']}/versions",
            json={"manifest": character_manifest(hero["id"])},
        )
        client.post(
            f"/api/packs/{scene['id']}/versions",
            json={"manifest": scene_manifest(hero["id"])},
        )
        candidate = client.post(
            "/api/candidates",
            json={
                "character_versions": {
                    "BOT1": [character["id"], 1],
                    "BOT2": [character2["id"], 1],
                },
                "scene_pack_id": scene["id"],
                "scene_version": 1,
                "hero_asset_id": hero["id"],
            },
        ).json()
        client.post(
            f"/api/candidates/{candidate['id']}/approve",
            json={"canonical": True, "review_note": "approved"},
        )
        baseline = client.post(
            "/api/baselines", json={"cast_key": candidate["cast_key"]}
        ).json()

        service = app.state.services.baselines
        original_load = service.load

        def load_then_tamper(baseline_id):
            loaded = original_load(baseline_id)
            loaded.manifest_path.write_bytes(b"changed after verification")
            return loaded

        service.load = load_then_tamper
        response = client.get(
            f"/api/baselines/{baseline['id']}/download/manifest"
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "integrity_error"


def test_browser_ui_exposes_asset_inventory_and_image_previews(tmp_path):
    with manager_client(create_app(tmp_path / "data")) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text

    assert 'id="assets"' in html
    assert "Uploaded asset inventory" in html
    assert "/content" in javascript
    assert 'document.createElement("img")' in javascript
    assert "Use in version manifest" in javascript
    assert "Copy ID" in javascript


def test_only_current_root_is_serialized_and_selectable_as_canonical(tmp_path):
    with manager_client(create_app(tmp_path / "data")) as client:
        hero = upload(client, "hero.png")
        character = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT1"}
        ).json()
        character2 = client.post(
            "/api/packs", json={"kind": "character", "name": "BOT2"}
        ).json()
        scene = client.post(
            "/api/packs", json={"kind": "scene", "name": "Studio"}
        ).json()
        client.post(
            f"/api/packs/{character['id']}/versions",
            json={"manifest": character_manifest(hero["id"])},
        )
        client.post(
            f"/api/packs/{character2['id']}/versions",
            json={"manifest": character_manifest(hero["id"])},
        )
        client.post(
            f"/api/packs/{scene['id']}/versions",
            json={"manifest": scene_manifest(hero["id"])},
        )
        candidate_body = {
            "character_versions": {
                "BOT1": [character["id"], 1],
                "BOT2": [character2["id"], 1],
            },
            "scene_pack_id": scene["id"],
            "scene_version": 1,
            "hero_asset_id": hero["id"],
        }
        never_canonical = client.post(
            "/api/candidates", json=candidate_body
        ).json()
        client.post(
            f"/api/candidates/{never_canonical['id']}/approve",
            json={"canonical": False, "review_note": "approved only"},
        )
        superseded = client.post("/api/candidates", json=candidate_body).json()
        client.post(
            f"/api/candidates/{superseded['id']}/approve",
            json={"canonical": True, "review_note": "first canonical"},
        )
        current = client.post("/api/candidates", json=candidate_body).json()
        current_response = client.post(
            f"/api/candidates/{current['id']}/approve",
            json={"canonical": True, "review_note": "replacement canonical"},
        )
        made_canonical = client.post(
            f"/api/candidates/{never_canonical['id']}/canonical"
        )

        by_id = {
            candidate["id"]: candidate
            for candidate in client.get("/api/candidates").json()
        }
        javascript = client.get("/static/app.js").text

    assert made_canonical.status_code == 200
    assert made_canonical.json()["is_current_canonical"] is True
    assert by_id[never_canonical["id"]]["is_current_canonical"] is True
    assert by_id[superseded["id"]]["is_current_canonical"] is False
    assert by_id[current["id"]]["is_current_canonical"] is False
    assert current_response.json()["is_current_canonical"] is True
    assert (
        "state.candidates.filter((item) => item.is_current_canonical)"
        in javascript
    )


def test_browser_ui_has_safe_mutations_practical_selectors_and_variant_review(tmp_path):
    with manager_client(create_app(tmp_path / "data")) as client:
        html = client.get("/").text
        javascript = client.get("/static/app.js").text

    assert 'name="invariants_verified"' in html or "invariants_verified" in javascript
    assert "X-Runtime-Manager" in javascript
    assert "Make canonical" in javascript
    assert "Current canonical" in javascript
    assert "Approved root" in javascript
    assert "character-version-options" in html
    assert "scene-version-options" in html
    assert "cast-options" in html
    assert (
        '{"palette": ["red", "green"], '
        '"accessories": {"BOT1": ["hat"]}}'
    ) in html
    assert '"accessories": ["hat"]' not in html


def test_web_assets_are_declared_as_wheel_package_data():
    pyproject = (
        __import__("pathlib").Path(__file__).parents[1] / "pyproject.toml"
    ).read_text()

    assert '[tool.setuptools.package-data]' in pyproject
    assert '"pack_manager"' in pyproject
    assert '"web/*.html"' in pyproject
    assert '"web/*.js"' in pyproject
    assert '"web/*.css"' in pyproject


def test_every_mutating_openapi_operation_requires_manager_header(tmp_path):
    schema = create_app(tmp_path / "data").openapi()
    mutating = {"post", "put", "patch", "delete"}
    operations = [
        operation
        for path in schema["paths"].values()
        for method, operation in path.items()
        if method in mutating
    ]

    assert operations
    for operation in operations:
        matching = [
            parameter
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "header"
            and parameter.get("name") == "X-Runtime-Manager"
        ]
        assert len(matching) == 1
        assert matching[0]["required"] is True


def test_readme_documents_current_api_security_and_errors():
    readme = (
        __import__("pathlib").Path(__file__).parents[1] / "README.md"
    ).read_text()

    assert "X-Runtime-Manager: 1" in readme
    assert "POST /api/candidates/{id}/canonical" in readme
    assert "DELETE /api/baselines/{id}" in readme
    assert "request_too_large" in readme
