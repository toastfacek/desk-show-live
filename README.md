# Desk Show MVP — one robot host, fal H3 Max

A single Python program that runs a one-host live loop: a hosted LLM writes each line,
fal MiniMax H3 Max performs it as a 5s 768p talking-head clip, and a local player plays
clips back-to-back while the next one generates. See the TDD in this repo for the full
design; `DECISIONS.md` for every ambiguity resolved before build; `OBS.md` for the
OBS/streaming path.

## Setup

```bash
pip install -r requirements.txt        # python 3.10+
# ffmpeg and (for the default player) mpv on PATH
export FAL_KEY=...                     # env only, never config/repo
export WRITER_API_KEY=...              # for the OpenAI-compatible writer endpoint
```

## Run order

```bash
# 0. Free full-loop shakeout — no fal calls, local test clips, $0:
python3 run_live.py --dry-run

# M0: bake hero.png + hold.mp4 (~$1–2, re-run --force until the design looks right):
python3 bake_assets.py

# M1: one real take (chains on the manifest across runs):
python3 run_live.py --turns 1

# M2/E5: the 60s live run (12 turns):
python3 run_live.py

# E6: forced hold — kill take 5 in flight, watch the freeze-frame recover:
python3 run_live.py --force-hold-at 5
```

## Experiments (M3)

```bash
python3 experiments/gen_takes.py --mode chain     # 8 scripted takes, pure chain (E1–E3, E4a)
python3 experiments/gen_takes.py --mode reset5    # 8 takes, re-anchor every 5 (E4b)
python3 experiments/e1_verbatim.py --dir out/exp/chain   # verbatim delivery (whisper or by ear)
python3 experiments/e4_contact_sheet.py --dir out/exp/chain
python3 experiments/e4_contact_sheet.py --dir out/exp/reset5
python3 experiments/e7_cost.py                    # real $/min + timing distributions
```

E2/E3 (voice drift, effect masking) are listening tests over the same chain takes:
raw `NNN.mp4` vs treated `NNN_fx.mp4` in `out/exp/chain/`.

## The knobs

Everything lives in `config.yaml`: writer endpoint/model (two lines to swap models),
persona, topics, anchor reset cadence, the frozen voice filtergraph, spend rate + hard
cap ($20 default — the meter refuses to submit past it and resumes prior spend from the
manifest), and the player (`mpv` | `folder` | `none`).

`out/takes.jsonl` is the measurement deliverable — every take, timing, and dollar.

## Tests

```bash
pip install pytest && python3 -m pytest tests/ -v   # unit + zero-spend full-loop smoke
```
