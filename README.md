# Desk Show

**Current `main` is two-host Runtime.** Pictures for PHASEONE[lol] and deb live in Pack Manager, not in git. See [`ASSETS.md`](ASSETS.md).

| Piece | Path |
| :---- | :---- |
| Hosts, scenes, locked hero | `pack-manager/` (`data/` is gitignored) |
| OBS clock | `obs-harness/` |
| Live flight | `runtime-flight/` |
| Prompt-safe sheets (words only) | `studio.yaml` |

The one-host prototype (`run_live.py`, `bake_assets.py`) is still in this repo. Do not look there for the two hosts.

---

# Desk Show — MVP

A single-host live desk-show prototype: a hosted LLM writes each line, fal
MiniMax H3 Max performs it as a 5s 768p talking-head clip, and a local
player plays clips back-to-back while the next one generates.

Full design and rationale: [`Desk Show — H3 Max Spec + Review + Drift Plan.md`](<Desk Show — H3 Max Spec + Review + Drift Plan.md>).
Implementation spec: [`Desk Show MVP — TDD (H3 Max, one robot host).md`](<Desk Show MVP — TDD (H3 Max, one robot host).md>).

## What this proves

1. Play-while-generating: 60s of continuous playback, no stall.
2. Verbatim line delivery: does H3 Max actually say the line it's given.
3. Identity drift: face drift across a last-frame chain, voice drift on raw audio.
4. Real $/min, including retries.

## Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in FAL_KEY and WRITER_API_KEY
```

You'll also need `ffmpeg` and `mpv` on PATH.

Edit `config.yaml`: at minimum set `writer.base_url` / `writer.model` to a
real OpenAI-compatible endpoint.

## Run

```
python bake_assets.py          # one-time: hero.png + hold.mp4
python run_live.py             # live loop, runs until spend cap or Ctrl-C
python run_live.py --max-takes 12 --no-player   # headless test run
```

Output lands in `out/`: `raw/` (untouched fal output), `ready/` (what the
playhead plays), `frames/` (last-frame PNG chain), `takes.jsonl` (the
manifest — this is the measurement deliverable).

## Day-one experiments (TDD §7)

```
python experiments/e1_verbatim.py       # generates 8 scripted takes
python experiments/e2_voice_drift.py    # raw audio for blind listen
python experiments/e3_voice_effect.py   # same takes through the robot filter
python experiments/e4_face_drift.py     # pure chain vs reset-every-5 contact sheets
python experiments/e5_60s_live_run.py   # 12-turn live run
python experiments/e6_forced_hold.py    # simulates a killed in-flight generation
python experiments/e7_cost.py           # $/min + retry overhead from a manifest
```

## Repo layout

```
config.yaml          persona, topics, rates, caps, toggles
run_live.py           the live loop (asyncio)
writer.py            LLM line writer
generator.py         fal H3 Max image-to-video wrapper
post.py              last-frame extraction/upload + robot voice filtergraph
playhead.py          mpv IPC
spend.py             cost tracking + hard cap
bake_assets.py       one-time hero still + hold clip
experiments/         day-one test scripts
assets/               hero.png, hold.mp4 (generated, not committed)
out/                  raw/ready/frames clips + takes.jsonl (generated, not committed)
```

## Non-goals (v1)

Second host, tweet ticker, chroma-key cutout, OBS, streaming, monetization,
15s clips, official MiniMax H3 on the live path. See the spec's v2 backlog.
