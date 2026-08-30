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

## Remaining-findings fix wave

The follow-up review was handled test-first. New coverage includes exact
two-host candidate contracts, strict variant section shapes, corrupted runtime
slot metadata, active-export cleanup exclusion, all requested concurrency
cases, OpenAPI mutation headers, and cast-scoped browser selection behavior.

RED:

```text
python3 -m pytest tests/test_candidates.py tests/test_packs.py \
  tests/test_assets.py tests/test_baselines.py tests/test_api.py \
  tests/test_web_js.py -q
20 failed, 122 passed in 2.75s
```

An initial focused GREEN run found one formatting-sensitive JavaScript source
assertion (`1 failed, 142 passed`); the assertion was corrected to test behavior
markers independently rather than source formatting.

Final verification:

```text
cd pack-manager && python3 -m pytest -q -W error
143 passed in 2.68s

cd obs-harness && python3 -m pytest -q
18 passed in 0.06s

cd pack-manager && node --check pack_manager/web/app.js
PASS

cd pack-manager && node --check pack_manager/web/selection.js
PASS

cd pack-manager && python3 -m compileall -q pack_manager tests
PASS

git diff --check
PASS

git diff --name-only abb2937..HEAD -- obs-harness
PASS (no output; no obs-harness changes)
```

Additional commits:

- `f9220c7` Enforce two-host contracts and race-safe exports
- `feb6cf6` Harden two-host web workflow and API docs
- `9f9ed9d` Make dropdown behavior assertion formatting-independent

The manager-wide export lock uses POSIX `fcntl.flock`, matching the documented
macOS, Linux, and WSL target. There are no unresolved concerns for that target.

## Final acceptance fix wave

Added test-first coverage for deterministic BOT1/BOT2 cast identity, normalized
nonblank pack names, an API-valid browser variant default, and payload-to-
manifest pack metadata consistency.

RED:

```text
python3 -m pytest tests/test_candidates.py tests/test_packs.py \
  tests/test_api.py tests/test_baselines.py -q
12 failed, 128 passed in 2.80s
```

The first focused GREEN run exposed one remaining legacy wrong-cast test that
still used JSON key insertion order (`1 failed, 139 passed`). It was corrected
to swap the actual BOT1/BOT2 assignments. The focused suites then passed:

```text
python3 -m pytest tests/test_candidates.py tests/test_packs.py \
  tests/test_api.py tests/test_baselines.py -q
140 passed in 2.54s
```

Final verification:

```text
cd pack-manager && python3 -m pytest -q -W error
154 passed in 2.85s

cd obs-harness && python3 -m pytest -q
18 passed in 0.06s

cd pack-manager && node --check pack_manager/web/app.js
PASS

cd pack-manager && node --check pack_manager/web/selection.js
PASS

cd pack-manager && python3 -m compileall -q pack_manager tests
PASS

git diff --check
PASS

git diff --name-only 291ff50..HEAD -- obs-harness
PASS (no output; no obs-harness changes)
```

Additional commits:

- `e7d6b76` Close final Character Pack Manager acceptance gaps
- `e5073f8` Align wrong-cast test with normalized slot identity

No unresolved concerns.
