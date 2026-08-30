# Character Pack and Baseline Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local browser tool that versions Character and Scene Packs, approves canonical and themed baseline candidates, and locks hash-verifiable immutable run baselines.

**Architecture:** A new `pack-manager` Python package sits beside `obs-harness`. FastAPI handles the local HTTP surface, while framework-free services own SQLite metadata, content-addressed files, candidate state transitions, invariant checks, baseline selection, export, and loading.

**Tech Stack:** Python 3.11+, SQLite, PyYAML, FastAPI, Uvicorn, python-multipart, pytest, HTTPX, HTML/CSS/vanilla JavaScript.

## Global Constraints

- Bind the web server to `127.0.0.1` by default.
- `obs-harness` behavior and public package boundaries must remain unchanged.
- Pack versions and locked run baselines are immutable.
- Character slots must not silently swap.
- Daily variants may change scene, palette, and approved accessories; they may not change silhouette, eye design, or proportions.
- Missing or unapproved variants must fall back to the approved canonical base.
- Binary assets are content-addressed by SHA-256 and are never overwritten.
- Locked exports use relative paths and include SHA-256 for every file.
- No fal, OpenAI, or OBS dependency is allowed in the default package.
- Tests use temporary directories, temporary SQLite databases, and a zero-cost provider.

---

### Task 1: Package foundation, database, and asset store

**Files:**
- Create: `pack-manager/pyproject.toml`
- Create: `pack-manager/.gitignore`
- Create: `pack-manager/pack_manager/__init__.py`
- Create: `pack-manager/pack_manager/errors.py`
- Create: `pack-manager/pack_manager/db.py`
- Create: `pack-manager/pack_manager/assets.py`
- Create: `pack-manager/tests/conftest.py`
- Create: `pack-manager/tests/test_assets.py`

**Interfaces:**
- Produces: `Database(path).connect()`, `Database.initialize()`
- Produces: `AssetStore(data_dir, database).put_bytes(filename, content, mime_type) -> Asset`
- Produces: `AssetStore.get(asset_id) -> Asset`
- `Asset` fields: `id`, `sha256`, `mime_type`, `size`, `path`, `created_at`

- [ ] **Step 1: Add packaging and test dependencies**

Create `pyproject.toml` with Python `>=3.11`, runtime dependencies `fastapi`, `uvicorn`, `python-multipart`, and `pyyaml`, and dev dependencies `pytest` and `httpx`. Configure pytest with `pythonpath = ["."]` and `testpaths = ["tests"]`.

- [ ] **Step 2: Write failing asset tests**

```python
def test_same_bytes_are_deduplicated(asset_store):
    first = asset_store.put_bytes("one.png", PNG, "image/png")
    second = asset_store.put_bytes("two.png", PNG, "image/png")
    assert first.id == second.id
    assert first.sha256 == second.sha256

def test_rejects_unsupported_mime(asset_store):
    with pytest.raises(ValidationError, match="unsupported image type"):
        asset_store.put_bytes("payload.txt", b"x", "text/plain")

def test_rejects_oversized_upload(asset_store):
    with pytest.raises(ValidationError, match="exceeds"):
        asset_store.put_bytes("huge.png", b"x" * 1025, "image/png")
```

- [ ] **Step 3: Run the focused tests and confirm RED**

Run: `python3 -m pytest tests/test_assets.py -q`

Expected: import failure because `pack_manager.assets` does not exist.

- [ ] **Step 4: Implement schema and content-addressed storage**

`Database.initialize()` creates `assets`, `packs`, `pack_versions`, `candidates`, `baselines`, and `canonical_candidates` tables in one transaction. `AssetStore` accepts PNG, JPEG, and WebP, enforces a configurable byte limit, hashes content, writes atomically through a temporary file, and inserts with `INSERT OR IGNORE`.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `python3 -m pytest tests/test_assets.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pack-manager
git commit -m "Add pack manager storage foundation"
```

---

### Task 2: Immutable Character and Scene Pack versions

**Files:**
- Create: `pack-manager/pack_manager/packs.py`
- Create: `pack-manager/tests/test_packs.py`

**Interfaces:**
- Consumes: `Database`, `AssetStore`
- Produces: `PackService.create_pack(kind: str, name: str) -> Pack`
- Produces: `PackService.create_version(pack_id: str, manifest: dict) -> PackVersion`
- Produces: `PackService.get_version(pack_id: str, version: int) -> PackVersion`
- Produces: `PackService.list_packs(kind: str | None = None) -> list[Pack]`

- [ ] **Step 1: Write failing pack tests**

```python
def test_versions_are_monotonic_and_immutable(pack_service):
    pack = pack_service.create_pack("character", "PHASEONE[lol]")
    v1 = pack_service.create_version(pack.id, character_manifest())
    changed = character_manifest()
    changed["persona"] = "More curious."
    v2 = pack_service.create_version(pack.id, changed)
    assert (v1.version, v2.version) == (1, 2)
    assert pack_service.get_version(pack.id, 1).manifest["persona"] != "More curious."

def test_character_manifest_requires_locked_traits(pack_service):
    pack = pack_service.create_pack("character", "deb")
    with pytest.raises(ValidationError, match="locked_traits"):
        pack_service.create_version(pack.id, {"persona": "Curious"})

def test_scene_manifest_requires_frame(pack_service):
    pack = pack_service.create_pack("scene", "Light studio")
    with pytest.raises(ValidationError, match="frame"):
        pack_service.create_version(pack.id, {"set": "Warm studio"})
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python3 -m pytest tests/test_packs.py -q`

Expected: import failure because `pack_manager.packs` does not exist.

- [ ] **Step 3: Implement pack validation and append-only versions**

Character manifests require `visual_invariants.locked_traits` containing exactly `silhouette`, `eye_design`, and `proportions`, plus `persona`, `writer_rules`, `voice_direction`, and `asset_ids`. Scene manifests require `set`, `palette`, `lighting`, `frame.w`, `frame.h`, `frame.fps`, `reanchor_every`, and `asset_ids`. Every asset ID must exist.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `python3 -m pytest tests/test_packs.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add pack-manager/pack_manager/packs.py pack-manager/tests/test_packs.py
git commit -m "Add immutable character and scene packs"
```

---

### Task 3: Candidate workflow, canonical bases, and variants

**Files:**
- Create: `pack-manager/pack_manager/providers.py`
- Create: `pack-manager/pack_manager/candidates.py`
- Create: `pack-manager/tests/test_candidates.py`
- Create: `pack-manager/tests/test_provider.py`

**Interfaces:**
- Consumes: `Database`, `AssetStore`, `PackService`
- Produces: `GenerationProvider.generate_still(...) -> Path`
- Produces: `ReferenceCopyProvider.generate_still(...) -> Path`
- Produces: `CandidateService.create(...) -> Candidate`
- Produces: `CandidateService.approve(candidate_id, *, canonical: bool, review_note: str) -> Candidate`
- Produces: `CandidateService.reject(candidate_id, *, review_note: str) -> Candidate`
- Produces: `CandidateService.resolve(cast_key, requested_candidate_id=None) -> CandidateResolution`

- [ ] **Step 1: Write failing candidate transition tests**

```python
def test_only_draft_candidate_can_be_approved(candidate_service, canonical_candidate):
    approved = candidate_service.approve(
        canonical_candidate.id, canonical=True, review_note="M0 passed"
    )
    with pytest.raises(ConflictError, match="draft"):
        candidate_service.reject(approved.id, review_note="changed mind")

def test_rejection_does_not_replace_canonical(candidate_service, approved_canonical, draft_variant):
    candidate_service.reject(draft_variant.id, review_note="wrong palette")
    resolution = candidate_service.resolve(approved_canonical.cast_key)
    assert resolution.candidate.id == approved_canonical.id

def test_unapproved_requested_variant_falls_back(candidate_service, approved_canonical, draft_variant):
    resolution = candidate_service.resolve(
        approved_canonical.cast_key, requested_candidate_id=draft_variant.id
    )
    assert resolution.candidate.id == approved_canonical.id
    assert resolution.fallback_reason == "requested candidate is not approved"
```

- [ ] **Step 2: Write failing invariant tests**

```python
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
```

- [ ] **Step 3: Run focused tests and confirm RED**

Run: `python3 -m pytest tests/test_candidates.py tests/test_provider.py -q`

Expected: import failures because candidate and provider modules do not exist.

- [ ] **Step 4: Implement provider protocol and reference-copy provider**

The provider requires at least one reference path, copies the first reference atomically to `output_path`, and never imports a vendor package.

- [ ] **Step 5: Implement candidate state machine**

Compute `cast_key` from ordered slot, pack ID, and version tuples plus scene pack/version. Validate all referenced versions and hero assets. A variant inherits the canonical cast key and records only allowed scene, palette, and accessory changes.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run: `python3 -m pytest tests/test_candidates.py tests/test_provider.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pack-manager/pack_manager/providers.py pack-manager/pack_manager/candidates.py pack-manager/tests/test_candidates.py pack-manager/tests/test_provider.py
git commit -m "Add baseline candidate and variant workflow"
```

---

### Task 4: Immutable baseline export, fallback, and verification

**Files:**
- Create: `pack-manager/pack_manager/baselines.py`
- Create: `pack-manager/tests/test_baselines.py`

**Interfaces:**
- Consumes: `Database`, `AssetStore`, `PackService`, `CandidateService`
- Produces: `BaselineService.lock_run(cast_key, requested_candidate_id=None) -> Baseline`
- Produces: `BaselineService.load(baseline_id: str) -> LoadedBaseline`
- Produces: `BaselineService.verify(baseline_id: str) -> None`

- [ ] **Step 1: Write failing export and immutability tests**

```python
def test_lock_run_exports_selected_approved_variant(
    baseline_service, approved_canonical, approved_variant
):
    baseline = baseline_service.lock_run(
        approved_canonical.cast_key, requested_candidate_id=approved_variant.id
    )
    manifest = json.loads(baseline.manifest_path.read_text())
    assert manifest["candidate_id"] == approved_variant.id
    assert manifest["canonical_candidate_id"] == approved_canonical.id
    assert manifest["fallback_reason"] is None

def test_lock_run_records_canonical_fallback(
    baseline_service, approved_canonical, draft_variant
):
    baseline = baseline_service.lock_run(
        approved_canonical.cast_key, requested_candidate_id=draft_variant.id
    )
    manifest = json.loads(baseline.manifest_path.read_text())
    assert manifest["candidate_id"] == approved_canonical.id
    assert manifest["fallback_reason"] == "requested candidate is not approved"

def test_locked_export_rejects_tampering(baseline_service, locked_baseline):
    locked_baseline.hero_path.write_bytes(b"tampered")
    with pytest.raises(IntegrityError, match="hash mismatch"):
        baseline_service.verify(locked_baseline.id)

def test_locked_baseline_cannot_be_deleted(database, locked_baseline):
    with pytest.raises(sqlite3.IntegrityError):
        database.connect().execute(
            "DELETE FROM baselines WHERE id = ?", (locked_baseline.id,)
        )
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `python3 -m pytest tests/test_baselines.py -q`

Expected: import failure because `pack_manager.baselines` does not exist.

- [ ] **Step 3: Implement atomic export**

Write into `data/exports/.tmp-<baseline_id>`, copy the hero and every referenced pack asset, write normalized JSON with sorted keys, compute file hashes, rename the directory atomically, insert the locked row, and install SQLite triggers that abort baseline updates and deletes.

- [ ] **Step 4: Implement verified loader**

Resolve only relative paths inside the export directory. Recompute every SHA-256 and raise `IntegrityError` on missing files, path escape, or mismatch.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `python3 -m pytest tests/test_baselines.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add pack-manager/pack_manager/baselines.py pack-manager/tests/test_baselines.py
git commit -m "Add immutable baseline exports"
```

---

### Task 5: Local API and browser manager

**Files:**
- Create: `pack-manager/pack_manager/app.py`
- Create: `pack-manager/pack_manager/web/index.html`
- Create: `pack-manager/pack_manager/web/app.js`
- Create: `pack-manager/pack_manager/web/style.css`
- Create: `pack-manager/tests/test_api.py`
- Create: `pack-manager/tests/test_no_vendor_clients.py`
- Create: `pack-manager/config.yaml`
- Create: `pack-manager/README.md`

**Interfaces:**
- Consumes: all services from Tasks 1–4
- Produces: `create_app(data_dir: Path) -> FastAPI`
- Produces HTTP endpoints under `/api/packs`, `/api/assets`, `/api/candidates`, and `/api/baselines`

- [ ] **Step 1: Write failing API workflow test**

The test must use `TestClient` to:

1. create two character packs and one scene pack;
2. upload one PNG asset per pack;
3. create pack versions;
4. upload a hero candidate;
5. create and approve a canonical candidate;
6. create a draft themed variant;
7. request a run using that unapproved variant;
8. assert the returned manifest uses the canonical candidate and records the fallback reason;
9. fetch and verify the locked baseline.

- [ ] **Step 2: Write failing upload and conflict API tests**

Assert unsupported MIME returns `422`, missing records return `404`, illegal state transitions and locked mutation attempts return `409`, and an oversized upload returns `413`.

- [ ] **Step 3: Run focused tests and confirm RED**

Run: `python3 -m pytest tests/test_api.py tests/test_no_vendor_clients.py -q`

Expected: import failure because `pack_manager.app` does not exist.

- [ ] **Step 4: Implement FastAPI dependency wiring and routes**

Use generated IDs, Pydantic request models at the HTTP boundary, `UploadFile` for images, and one exception handler mapping domain errors to stable JSON:

```json
{"error": {"code": "conflict", "message": "candidate is not draft"}}
```

Do not return absolute filesystem paths. Baseline download routes may return only files verified by `BaselineService`.

- [ ] **Step 5: Implement the plain browser UI**

The page must expose pack lists, version forms, asset upload, candidate upload/generation, approve/reject/canonical controls, variant creation, run lock, and manifest inspection. Use semantic forms and `fetch`; no frontend build step.

- [ ] **Step 6: Add vendor-boundary test**

Scan `pack_manager/` for imports containing `fal`, `openai`, `obsws`, or `requests`. The test fails if any appear in the default package.

- [ ] **Step 7: Run manager tests and confirm GREEN**

Run: `python3 -m pytest -q`

Expected: all `pack-manager` tests pass.

- [ ] **Step 8: Run repository regression tests**

Run: `cd ../obs-harness && python3 -m pytest -q`

Expected: all existing OBS harness tests pass unchanged.

- [ ] **Step 9: Manually verify the browser workflow**

Run: `python3 -m pack_manager.app --config config.yaml`, open `http://127.0.0.1:8765`, and complete the canonical-base and fallback workflow from the API test using the forms.

- [ ] **Step 10: Commit**

```bash
git add pack-manager
git commit -m "Add local character pack manager"
```

---

## Final verification

- [ ] Run `python3 -m pytest -q` in `pack-manager`.
- [ ] Run `python3 -m pytest -q` in `obs-harness`.
- [ ] Run `git diff --check origin/main...HEAD`.
- [ ] Confirm `pack-manager/data/` and Python caches are ignored.
- [ ] Confirm no secrets or absolute local paths appear in tracked files.
- [ ] Confirm the browser binds to `127.0.0.1`.
- [ ] Confirm a locked baseline export remains unchanged after canonical replacement.
