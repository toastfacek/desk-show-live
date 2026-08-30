# Character Pack Manager

A local FastAPI manager for immutable character and scene pack versions, reviewed
hero candidates, themed variants, and hash-verified run baseline exports. The
default generation provider copies an approved local reference; the package does
not call an image vendor, language model, or OBS.

## Run locally

Requires Python 3.11 or newer.

```bash
python3 -m pip install -e '.[dev]'
python3 -m pack_manager.app --config config.yaml
```

Open <http://127.0.0.1:8765>. The checked-in configuration permits local access
only. The CLI rejects any host other than `127.0.0.1`.

Data is written below `data/`, which is git-ignored. Uploaded image names never
become filesystem paths: PNG, JPEG, and WebP content is size-limited, hashed,
checked against the claimed format's file signature, and stored by SHA-256.
Do not place secrets in `config.yaml` or pack manifests.

## Browser workflow

1. Create character and scene packs.
2. Upload pack references and create each pack's immutable version from JSON.
3. Upload a clean hero image and create a draft candidate, or generate one by
   selecting a local reference.
4. Approve or reject the draft. Choose **Approve canonical** for the cast's
   canonical base.
5. Create an optional themed variant from the canonical candidate and review it.
6. Lock a run by cast key. An absent, rejected, or draft requested variant
   automatically falls back to the canonical candidate and records why.
7. Inspect or download the verified manifest from the locked run card.

Locked exports are self-contained under `data/exports/<baseline-id>/`. They use
relative paths and SHA-256 records. The application verifies all records before
returning or downloading a manifest.

## HTTP API

The interactive OpenAPI reference is available at `/docs`. Every `POST`, `PUT`,
`PATCH`, or `DELETE` request under `/api/` must include
`X-Runtime-Manager: 1`. Read-only requests do not require it.

- `GET /api/packs`
- `POST /api/packs`
- `GET /api/packs/{pack_id}/versions`
- `POST /api/packs/{pack_id}/versions`
- `GET /api/packs/{pack_id}/versions/{version}`
- `GET /api/assets`
- `POST /api/assets`
- `GET /api/assets/{id}`
- `GET /api/assets/{id}/content` (hash-verified image bytes for previews)
- `GET /api/candidates`
- `POST /api/candidates`
- `GET /api/candidates/{id}`
- `POST /api/candidates/generate`
- `POST /api/candidates/variants`
- `POST /api/candidates/{id}/approve`
- `POST /api/candidates/{id}/reject`
- `POST /api/candidates/{id}/canonical`
- `GET /api/baselines`
- `POST /api/baselines`
- `GET /api/baselines/{id}`
- `DELETE /api/baselines/{id}` (always reports immutable conflict)
- `GET /api/baselines/{id}/manifest`
- `GET /api/baselines/{id}/download/manifest`

Domain failures have a stable envelope:

```json
{"error":{"code":"conflict","message":"candidate is not draft"}}
```

The codes include `request_validation`, `malformed_request`,
`validation_error`, `upload_too_large`, `request_too_large`, `unsafe_request`,
`not_found`, `method_not_allowed`, `conflict`, `integrity_error`, and
`internal_error`. Framework routing, parsing, and request-model failures use
the same envelope. API responses never expose local absolute paths.

## Test

```bash
python3 -m pytest -q
```
