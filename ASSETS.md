# Where the two hosts live

PHASEONE[lol] and deb are not missing. They are not loose PNGs next to `studio.yaml`.

| What you want | Where it actually is |
| :---- | :---- |
| Prompt-safe sheets (words: silhouette, colour, no names in the prompt) | Root `studio.yaml`. **Reference only.** Not read by Pack Manager or `runtime-flight` as the live bible. |
| Character packs, scene packs, hero candidates, locked 1344×768 baseline | `pack-manager/` |
| Live image bytes on a machine that already approved them | `pack-manager/data/` — **gitignored**. Hashed blobs, not filenames. |
| A locked run you can hand to flight | `pack-manager/data/exports/<baseline-id>/` |
| Seed still for empty clones / this Cloud Agent environment | `pack-manager/fixtures/hero_wide.png` (1344×768). Lock it with `python3 -m pack_manager.hosts`. |
| OBS timing placeholders (not the hosts) | `obs-harness/assets/clips/*.mp4` |
| Old one-host bake (`hero.png`, `hold.mp4`) | Root `assets/` — also gitignored. `bake_assets.py` / `run_live.py`. Different show. |

`studio.yaml` still has `anchor: assets/hero_wide.png`. That path was never committed. Root `.gitignore` ignores `assets/*`. Pack Manager `data/` is ignored too. If you approved a hero on your laptop, it is still on that machine under `pack-manager/data/`. A fresh clone does not copy that directory.

This environment stages a demo from the checked-in seed:

```bash
./scripts/stage-demo.sh
```

That writes gitignored Pack Manager `data/` (PHASEONE[lol], deb, locked 1344×768 baseline) and the reviewed Dwarkesh source packet under `runtime-flight/inputs/`. It does not call fal or a text model.

M0: flight-ready Character/Scene Pack **v2** plus one approved, locked 1344×768 hero baseline in Pack Manager.

How to look at them:

```bash
cd pack-manager
python3 -m pip install -e '.[dev]'
python3 -m pack_manager.app --config config.yaml
# http://127.0.0.1:8765
```
