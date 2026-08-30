# Character Pack Manager final fix report

## Scope completed

- Added SQLite immutability triggers for pack-version updates and deletes.
- Tightened variant change validation to the three allowed top-level keys and
  recursive locked-trait rejection.
- Added alternate Scene Pack version selection while preserving canonical cast
  identity and lineage.
- Made variant approval revalidate changes, require explicit invariant
  verification, and transactionally reject stale canonical lineage.
- Added fixed v1 host mapping, exact pack-name display names, and downstream
  loader validation.
- Added transactional canonical selection for approved root candidates, with
  API and UI controls.
- Added pre-parser ASGI request limiting for declared and streamed bodies,
  separately configurable multipart overhead, trusted Host enforcement, a
  mutation marker, and same-origin mutation checks.
- Added practical pack/version/cast selectors, accurate candidate labels,
  isolated corrupt baseline listings, packaged web assets, and safe startup
  cleanup for temporary and unreferenced generated exports.

## TDD record

RED:

```text
python3 -m pytest tests/test_packs.py tests/test_candidates.py tests/test_baselines.py tests/test_api.py -q
25 failed, 80 passed, 1 error in 1.81s
```

An initial `python -m pytest ...` attempt could not run because this image has
`python3` but no `python` executable.

Focused GREEN:

```text
python3 -m pytest tests/test_packs.py tests/test_candidates.py tests/test_baselines.py tests/test_api.py -q
106 passed in 1.60s
```

After adding explicit concurrency coverage, the full verification result was:

```text
cd pack-manager && python3 -m pytest -q -W error
118 passed in 1.74s

cd obs-harness && python3 -m pytest -q
18 passed in 0.05s

cd pack-manager && node --check pack_manager/web/app.js
PASS

cd pack-manager && python3 -m compileall -q pack_manager tests
PASS

git diff --check
PASS
```

## Commits

- `6236e4e` Fix final Character Pack Manager review findings
- `d31c34f` Enforce streaming request limits before parsing
- `a189de7` Cover concurrent canonical and variant approval

## Concerns

No unresolved correctness concerns. `max_request_bytes` must remain greater
than `max_upload_bytes`; the default and checked-in config reserve 1 MiB for
multipart framing and headers.
