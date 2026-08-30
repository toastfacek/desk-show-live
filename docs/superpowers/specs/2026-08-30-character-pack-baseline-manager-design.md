# Character Pack and Baseline Manager Design

## Goal

Build a local tool that manages reusable character truth, reusable scene truth, optional themed daily variants, and the immutable baseline selected for a show run.

The tool is a Runtime-only sibling of `obs-harness`. It does not change the OBS clock, director, player protocol, writer, or fal video path. Downstream systems consume a locked baseline through a self-contained manifest.

## Terms

- **Character Pack:** one character's permanent identity: visual invariants, persona, writer rules, voice direction, approved references, and expression assets.
- **Scene Pack:** reusable studio truth: set description, palette, lighting, frame geometry, and optional deterministic OBS assets.
- **Pack Version:** an immutable snapshot of a Character or Scene Pack.
- **Candidate:** one proposed clean wide-shot baseline assembled from exact pack versions. It begins as `draft` and may become `approved` or `rejected`.
- **Canonical base:** the approved default candidate for one cast and scene combination.
- **Daily variant:** an approved candidate derived from a canonical base. It may change the set, palette, and approved accessories, but not character silhouette, eye design, or proportions.
- **Run Baseline:** an immutable export selected when a show starts. Every reset in that run returns to the same image and metadata.

## Scope

The first release includes:

1. A local web manager bound to `127.0.0.1`.
2. SQLite persistence and local content-addressed asset storage.
3. Character and Scene Pack creation and immutable versioning.
4. Reference image, expression-sheet, studio-plate, and hero-candidate uploads.
5. A replaceable still-generation provider interface.
6. A zero-cost reference-copy provider for rehearsal and tests.
7. Candidate creation, approval, rejection, canonical selection, and variant lineage.
8. Immutable run-baseline locking and self-contained export.
9. Canonical fallback when a requested variant is absent or unapproved.
10. A downstream reader that validates and loads a locked baseline manifest.

The first release does not call fal, a text model, OBS, or H3. It does not generate animation. It does not alter `obs-harness` behavior.

## Architecture

The manager lives in `pack-manager/`, separate from `obs-harness/`. Core domain and storage code have no web-framework or generation-vendor dependency.

```text
Browser
  -> local FastAPI application
  -> PackService / CandidateService / BaselineService
  -> SQLite metadata + content-addressed files
  -> immutable baseline export
  -> future live-sockets and OBS consumers
```

SQLite holds metadata and relationships. Binary assets are stored under `data/blobs/<sha256>.<ext>`. An asset is never overwritten. Pack versions and locked baselines are append-only.

## Data model

### Pack

```json
{
  "id": "char_phaseone",
  "kind": "character",
  "name": "PHASEONE[lol]",
  "created_at": "2026-08-30T18:00:00Z"
}
```

`kind` is `character` or `scene`.

### Pack version

```json
{
  "pack_id": "char_phaseone",
  "version": 1,
  "manifest": {
    "visual_invariants": {
      "body_shape": "broad rounded orange pebble",
      "eyes": "two solid cream ovals without pupils",
      "locked_traits": ["silhouette", "eye design", "proportions"]
    },
    "persona": "Calm, dry, optimistic technical anchor.",
    "writer_rules": ["Never claim certainty without evidence."],
    "voice_direction": "Measured, curious, warm.",
    "asset_ids": ["asset_..."]
  }
}
```

A version cannot be edited. Editing creates the next integer version.

### Candidate

A candidate records:

- exact character pack IDs and versions mapped to slots;
- exact scene pack ID and version;
- one clean wide-shot asset;
- `canonical_candidate_id` for variant lineage;
- optional theme and approved accessory changes;
- status: `draft`, `approved`, or `rejected`;
- review note and timestamps.

Character slot order is part of the cast key. `BOT1` and `BOT2` cannot silently swap.

### Run baseline

A run baseline records:

- a generated baseline ID;
- the approved candidate ID;
- the canonical fallback candidate ID;
- exact pack versions;
- selected hero asset path and SHA-256;
- frame dimensions and re-anchor interval;
- host-to-OBS mapping and display names;
- creation time;
- export manifest path and SHA-256.

Once locked, no field or exported file may change.

## Candidate and variant rules

1. Only a draft candidate may be approved or rejected.
2. A canonical candidate must be approved.
3. A daily variant must reference an approved canonical candidate with the same character slots and core Character Pack versions.
4. A variant may declare scene, palette, and accessory changes.
5. A variant may not override the locked character traits: silhouette, eye design, or proportions.
6. Approving a new canonical candidate does not mutate old baselines.
7. Rejecting a candidate leaves the previous canonical candidate unchanged.

## Baseline selection

At run start:

1. Resolve the canonical candidate for the requested cast and scene.
2. If an approved daily variant was explicitly selected, use it.
3. If the variant is missing, draft, rejected, or invalid, use the canonical candidate.
4. Copy the selected hero and exact pack manifests into a new export directory.
5. Write `manifest.json`, hash it, lock the database row, and return the baseline ID.

The running show receives only the baseline manifest path. It never follows mutable pack records.

## Export contract

```text
data/exports/<baseline_id>/
  manifest.json
  hero.png
  packs/
    BOT1.json
    BOT2.json
    scene.json
  assets/
    <content-addressed files>
```

`manifest.json` uses relative paths and includes SHA-256 for every exported file. A loader verifies all hashes before returning the baseline.

## Generation provider

```python
class GenerationProvider(Protocol):
    def generate_still(
        self,
        *,
        prompt: str,
        reference_paths: tuple[Path, ...],
        seed: int | None,
        output_path: Path,
    ) -> Path: ...
```

The default provider copies one selected reference image to the output path. This exercises the whole manager for free. Future fal or image-model providers implement the same interface in separate optional modules.

## Web manager

The web UI supports:

- listing and creating packs;
- viewing version history;
- creating a version from JSON fields and uploaded assets;
- uploading candidate images;
- invoking the configured provider;
- approving or rejecting candidates;
- marking an approved candidate canonical;
- creating a variant from the canonical base;
- locking a run baseline;
- inspecting and downloading the locked manifest.

The UI is deliberately plain. Correct asset lineage and safe state transitions matter more than visual polish.

## Failure handling

- Duplicate asset upload: return the existing content-addressed asset.
- Invalid pack kind or manifest: reject before writing a version.
- Missing referenced asset: reject candidate creation.
- Provider failure: leave no candidate and retain the canonical base.
- Invalid variant: reject approval with the violated invariant names.
- Missing/unapproved requested variant: lock the canonical fallback and record the fallback reason.
- Export interruption: remove the temporary export; no baseline row becomes locked.
- Hash mismatch when loading: refuse the baseline.
- Attempted update/delete of a locked baseline: return a conflict.

## Security

- Bind to `127.0.0.1` by default.
- Store no API secrets in SQLite, config, manifests, logs, or the repository.
- Sanitize uploaded filenames and never use them as storage paths.
- Limit upload size and accept only configured image MIME types.
- Do not serve arbitrary filesystem paths.
- Use generated IDs and content hashes, not user-controlled directory names.

## Testing

Tests use temporary directories, temporary SQLite databases, and the zero-cost provider. They cover:

- immutable pack versions;
- asset deduplication and upload validation;
- candidate state transitions;
- canonical replacement without history mutation;
- variant invariant enforcement;
- canonical fallback;
- byte-stable locked exports;
- hash verification and tamper rejection;
- locked-baseline mutation rejection;
- API workflow from pack creation through baseline lock;
- no fal, OpenAI, or OBS dependency in the default package.

## Acceptance criteria

The slice is complete when an operator can use the local browser to:

1. create two Character Packs and one Scene Pack;
2. upload their reference assets;
3. create immutable pack versions;
4. upload or generate a clean baseline candidate;
5. approve it as the canonical base;
6. create and approve an optional daily variant;
7. start a run with either the variant or canonical fallback;
8. load the exported manifest and verify every file hash;
9. prove through tests that the locked run cannot change.
