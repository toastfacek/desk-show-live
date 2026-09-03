# Current show

This is the lock. Older specs in this repo are history. If they disagree with this file, this file wins.

**Record only.** `stream.enabled` stays false. Do not stream.

## What is on the desk

One host: **PHASEONE[lol]** (`BOT1`). Orange software sprite. One mic. Blank monitor. Dark stream room. The right third of the 1344×768 still is empty for a chat well.

There is no second host. **deb** is not in the canonical lock. Chat is the other voice in the room.

| Piece | Truth |
| :---- | :---- |
| Host pack | Pack Manager character `BOT1` / `PHASEONE[lol]` |
| Scene | `Solo Stream Desk` |
| Seed still | `pack-manager/fixtures/hero_solo.png` (1344×768) |
| Live bytes | `pack-manager/data/` (gitignored). Lock with `python3 -m pack_manager.hosts` |
| Display names | Pack Manager only. Writer, discuss, chat picker, and H3 prompts never see `PHASEONE` or `deb` |
| Accent | Acid lemon `#D4E04A` on furniture / CG. Fal never sees program-out |
| HostMind model | `text.model` in `runtime-flight/config.local.yaml`. Slug is not a secret. Key stays in `TEXT_API_KEY`. |

BOT2 is still a valid optional slot so old two-host test fixtures lock. The live show does not use it.

## What the hour is

A Twitter list, tweet by tweet, until runway is gone.

Spine for each post, in this order, one spoken point at a time:

1. Read the load-bearing bit. Do not read the card aloud.
2. Say who posted it and what they are actually talking about.
3. Dissect the idea.
4. Name one broader theme.
5. Take a side.
6. After that spine, answer one selected chat comment if the picker handed one over.

Then the next tweet. Do not shuffle talking points to feed the GPU. Writer order is playback order.

The host is an AI analyst and the voice of the audience. Software, not a driver, not a user of the product. Privacy gets one honest pass. The rest of the time is what this enables.

## Chat picker

`--chat-file` is a JSON object:

```json
{
  "comments": [
    {"id": "c1", "author": "sam", "text": "Who actually posted this?"},
    {"id": "c2", "author": "lee", "text": "lol"}
  ]
}
```

`runtime_flight.chat_pick` calls the text model once per tweet. It may pick 0–3 comments that ask a real question, add a concrete fact, or poke a hole. It skips spam, plus-ones, emoji-only, insults, and off-topic noise. It may only use supplied ids. Invented ids fail the pick.

The writer receives `text` + `why` only. Chat is context, not a second host. If the picker fails, the rundown continues without chat.

The picker module does not import the writer, fal, the live harness, or OBS.

## How tape gets made

```
list URL or list file
    → load-list / content inbox (pending → claimed → done | dropped)
    → SegmentPlanner (package.json)
    → chat picker (optional)
    → Writer, BOT1 only, 2–8 turns (default 6)
    → fal H3 Max Turbo, serial await today
    → concat ready clips → rundown.mp4
```

Stop when runway is gone: spend cap, text budget, or empty inbox. `--until` is optional. Sunday is not the stop.

`run-list` does not talk to OBS. OBS is a player on a ready buffer, not the reason a take exists.

Cook may run in parallel later (cook-queue already has `max_inflight=4`). Playback still follows writer order. Do not glue cook to the playhead.

## Isolation

| Must not contain | Where |
| :---- | :---- |
| `writer` as a root import | `models.py` |
| Display names (`PHASEONE`, `deb`) | Writer system, discuss `HOST_SYSTEM`, chat picker |
| `host_a` / `host_b` | Writer and discuss source |
| fal / OBS / live harness | Chat picker, writer, discuss, list orchestrator |

Named shows stay in Pack Manager and overlay furniture. They never enter a prompt.

## Commands

Stage an empty clone (no fal, no text model):

```bash
./scripts/stage-demo.sh
```

Lock or replace the solo baseline:

```bash
python3 -m pack_manager.hosts --force --hero pack-manager/fixtures/hero_solo.png
```

Load a list without cooking:

```bash
python3 -m runtime_flight load-list \
  --inbox out/inbox \
  --list 'https://x.com/i/lists/<id>'
```

Comment the list until runway runs out. Record only. Confirm spend.

```bash
RUNTIME_ALLOW_PAID=1 python3 -m runtime_flight run-list \
  --config config.local.yaml \
  --inbox out/inbox \
  --list 'https://x.com/i/lists/<id>' \
  --chat-file chat.json \
  --turns 6 \
  --confirm-spend 8.00 \
  --confirm-text-requests 240 \
  --out out
```

Offline list snapshot: `--list-file` with `{list_id, tweets:[{url}, ...]}`.

X login is env `X_BEARER_TOKEN` or `TWITTER_BEARER_TOKEN`. Do not paste the token into chat.

Older paths still exist and are not the show:

| Command | What it is |
| :---- | :---- |
| `prepare-pass` / `cook-queue` | 3–6 staged tweets, 2–3 turns, ready buffer |
| `segment` | No-OBS paid segment |
| `smoke` / `live` | OBS 90s flight. Human-gated. Still two-shot furniture |
| `run_live.py` / `bake_assets.py` | Abandoned one-host prototype |

## What we already learned

A Stonks list run (80 tweets, 13:23 tape, $8 cap) was shallow because `--turns 2` plus “do not read the card aloud” collapsed every tweet into a shrug. All 160 spoken lines were BOT1 anyway. Two hosts were cheap on camera and expensive in the writer. Chat is the better second voice.

Mean fal inference was ~1.65s. Wall clock still lost to serial `await performer.start()` and to plan/write while fal sat idle. Overlapping cook is a follow-up. It is not a reason to shuffle points.

Invalid list tweets must drop and continue (`release_claimed()`), not crash the rundown.

## Open

- Port the cook-queue inflight loop into `orchestrator.py` (max 4). Do not add a third scheduler.
- Segment planner still knows how to write a two-host package. List playback stays on BOT1.
- OBS overlay still has two-host wells from the Light Media Club flight. Solo CG is not relocked.
- Do not commit `out/` or `pack-manager/data/`.

## Historical docs

Keep them. Do not treat them as the lock.

- `Desk Show — Two-Host Architecture & Harness.md`
- `Desk Show — Character & Set Bible.md`
- `Desk Show MVP — TDD (H3 Max, one robot host).md`
- `runtime-flight/LIVE_FLIGHT_CHECK.md` (first two-host OBS live)
- `research/findings/*`
