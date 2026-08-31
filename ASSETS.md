# Where the two hosts live

PHASEONE[lol] and deb are not missing. They are not in this git tree as pictures.

| What you want | Where it actually is |
| :---- | :---- |
| Prompt-safe sheets (words: silhouette, colour, no names in the prompt) | Root `studio.yaml`. **Reference only.** Not read by Pack Manager or `runtime-flight` as the live bible. |
| Character packs, scene packs, hero candidates, locked 1344×768 baseline | `pack-manager/` |
| The image bytes | `pack-manager/data/` — **gitignored**. Hashed blobs, not filenames. |
| A locked run you can hand to flight | `pack-manager/data/exports/<baseline-id>/` |
| OBS timing placeholders (not the hosts) | `obs-harness/assets/clips/*.mp4` |
| Old one-host bake (`hero.png`, `hold.mp4`) | Root `assets/` — also gitignored. `bake_assets.py` / `run_live.py`. Different show. |

`studio.yaml` still has `anchor: assets/hero_wide.png`. That path was never committed. Root `.gitignore` ignores `assets/*`. Pack Manager `data/` is ignored too. If you approved a hero on your machine, it is still on that machine under `pack-manager/data/`. Cloning this repo will not bring it back.

M0 on current `main`: flight-ready Character/Scene Pack **v2** plus one approved, locked 1344×768 hero baseline in Pack Manager — not a PNG dropped next to `studio.yaml`.

How to look at them:

```bash
cd pack-manager
python3 -m pip install -e '.[dev]'
python3 -m pack_manager.app --config config.yaml
# http://127.0.0.1:8765
```
