# Desk Show

**Current lock: [`SHOW.md`](SHOW.md).** Solo PHASEONE[lol], chat as the other voice, Twitter list until runway. Record only.

| Piece | Path |
| :---- | :---- |
| Current show | [`SHOW.md`](SHOW.md) |
| Host, scene, locked hero | `pack-manager/` — seed still `pack-manager/fixtures/hero_solo.png` |
| Asset map | [`ASSETS.md`](ASSETS.md) |
| Live flight | `runtime-flight/` |
| OBS clock | `obs-harness/` |
| Prompt-safe sheets (words only) | `studio.yaml` — reference, not the live bible |

## Run

Empty clone, no fal, no text model:

```bash
./scripts/stage-demo.sh
```

Comment a Twitter list (paid, record only):

```bash
RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight run-list \
  --config config.local.yaml \
  --inbox out/inbox \
  --list 'https://x.com/i/lists/<id>' \
  --chat-file chat.json \
  --turns 6 \
  --confirm-spend 8.00 \
  --confirm-text-requests 240
```

`stream.enabled` stays false. Do not stream. Do not commit `out/` or `pack-manager/data/`.

## Tests

```bash
PYTHONPATH=pack-manager:obs-harness:runtime-flight python3 -m pytest -q -W error pack-manager
PYTHONPATH=pack-manager:obs-harness:runtime-flight python3 -m pytest -q -W error runtime-flight
```

## History

The rest of the markdown in this repo is research and earlier locks: two-host Light Media Club, the one-host `run_live.py` prototype, OBS furniture notes. They stay for provenance. They are not the show.
