# TDD — Harness MVP (OBS sidecar, rehearse)

**Status:** Draft for build · **Date:** 30 Aug 2026 · **Owner:** Jesse

**Parent docs:** `Agentic Live Streaming Harness — Plan.md` (org chart), `Desk Show — Two-Host Architecture & Harness.md` (show design). This TDD is the first build slice of the harness only.

The older file `Desk Show MVP — TDD (H3 Max, one robot host).md` is a different slice: one host, a simple file player, real fal. Do not mix the two. That slice still matters for “does the video model say the line.” This slice is “does the clock and the switcher work with fake clips, at zero dollars.”

No code in this file. After it is accepted, implementation follows these contracts.

---

## 1. Overview and goals

A program on the same computer as OBS. It runs a 90-second show list in **rehearse** mode: no fal, no writer model, no producer model. A stub “performer” hands back existing video files after a fake delay. The director is a function. OBS is the player. We sit beside OBS. We do not fork it. We do not replace it.

**This slice proves four things:**

1. **The clock owns the cut.** At each clip edge the harness asks the player what is on air, the director returns one instruction, the harness does that instruction. A late text model cannot stall the cut. (There is no text model here; we still prove the cut does not wait.)
2. **Hold is a layout, not a crash.** When the next file is late on purpose, the picture goes to `card_full` or `hold`, the headline stays, the music stays, and the show continues when the file lands.
3. **OBS is a backend, not the program.** All player calls go through a small interface. Tests of the director and the loop use a fake player. OBS is only required for the live-on-the-desk checks.
4. **The split shares one play time.** In OBS, `split` uses one media source twice, left crop and right crop. Both halves stay in sync. If this fails, stop and do not build more layouts on a lie.

**Done when:**

- 90 seconds run unattended in `rehearse` with no dead air (no black frame, no frozen host face used as the “hold”).
- Hold fires at least once on purpose (stub delay longer than the clip).
- The log file has one row per take, including holds and the forced-late take.
- Director tests pass with the fake player (no OBS).
- Crop-sync check passes on a real OBS (or we write down that it failed and stop).

**Out of this slice**

fal, writer model, producer model, spend in real dollars, Twitch, a public installer, a custom switcher, creating or deleting OBS scenes from code, two paid pictures, chat driving the show.

Art approval (`hero_wide.png`) is **not** a gate for this slice. Rehearse plays canned files. The two-host look tests (E1 composition) stay on the other track. If those fail, the *show* changes. The harness contracts here still hold.

---

## 2. Locked decisions

| Decision | Choice |
| :---- | :---- |
| Where it runs | Jesse’s machine, next to OBS. macOS or Linux first. Windows later if needed. |
| Language | Python 3.11+, one process, asyncio. Same bet as the older TDD. |
| Player | OBS Studio 28+ (built-in remote-control port, protocol v5). Stock OBS. No fork, no plugin in this slice. |
| How we talk to OBS | A client library for that port (`obsws-python` or equal). Localhost. Password from the environment, never from the repo. |
| How the rest of the code sees the player | A `Player` interface (§4). OBS is one implementation. Tests use `FakePlayer`. |
| Director | Function. Snapshot in, one beat out. No model. |
| Producer | A file. The show list already contains the packages. |
| Writer | A file. A list of thoughts in order. The harness keeps two thoughts ready. |
| Performer | Stub. Copies a canned mp4 into `out/ready/` after a jittered delay. Cost always $0. |
| Mode | `rehearse` only. `live` and `replay` exist as names in config and are refused if selected. |
| Scenes | Built by hand once. Code may switch and fill. Code may not create, delete, or rename scenes. |
| Operator | A flag file or a single key in a tiny local page is enough: `hold`, `panic`. A full panel is not in this slice. |

---

## 3. System architecture

One process. Two loops. The short loop is the product.

```
Show list (file)
  → slow loop: load the next segment package into memory
  → writer slot: keep 2 thoughts from the script file

OBS (or FakePlayer)
  → short loop, every clip edge (~5s):
        snapshot = player.get_program_state()
        beat = director.decide(snapshot, show_state)
        harness.execute(beat)
        if beat.submit: performer.start(beat.submit)

Stub performer
  → after delay: file in out/ready/, row in out/takes.jsonl
  → next short loop sees it in snapshot.ready
```

The harness is the clock. It never asks an agent “is it time?” It asks the player.

Nothing on the short loop waits for a language model. In this slice there is no language model at all.

**Components**

| Name | Kind | Job |
| :---- | :---- | :---- |
| `run.py` | Loop | Reads config, runs slow + short loops, writes the log, exits clean. |
| `director.py` | Function | Snapshot + show state → one beat. |
| `player.py` | Interface | The command list. |
| `player_obs.py` | Backend | Talks to OBS. Reconnects if the port drops. |
| `player_fake.py` | Backend | In-memory player for tests. Advances time when told. |
| `performer_stub.py` | Function | Fake delay, then a canned file. |
| `rundown.yaml` | Data | Show list + packages. |
| `script.jsonl` | Data | Spoken thoughts, in order. |
| `posts.json` | Data | The one post the center card shows. |

---

## 4. The player interface

Every method the harness may call. No others in this slice.

```
get_program_state() -> ProgramState
set_layout(name)                    # wide | split | solo_l | solo_r | card_full | hold
play_clip(path)                     # absolute path the player can open
set_speaking(host | null)           # BOT1 | BOT2 | null
set_center(kind, data)              # tweet_card | none   (other kinds later)
set_headline(text)
set_name_bar(host, name, handle)
duck_music(db)
```

Deferred (do not implement now): `set_ticker`, `play_sting`, `set_crop` as a live cut. Crop is set by hand in the scene. Tickers can be static in the scene.

**`ProgramState`**

```json
{
  "t": 12.4,
  "layout": "split",
  "on_air": {
    "kind": "host",
    "path": "/abs/out/ready/002.mp4",
    "take": 2,
    "duration_s": 5.0,
    "ends_at": 15.0,
    "media_ok": true
  },
  "connected": true
}
```

`on_air.kind` is `host` | `card` | `hold` | `none`.  
`media_ok` is false if the source is missing or the file failed to open.  
`t` is seconds from harness start, not wall clock. The fake player and the real loop must use the same meaning.

**OBS mapping (implementation, not a second API)**

| Call | OBS |
| :---- | :---- |
| `set_layout(name)` | Switch the current scene to the scene of that name. |
| `play_clip(path)` | Set the local file on input `HOST_WIDE`. Restart playback from the start. |
| `set_speaking(host)` | Show the highlight item for that host; hide the other. |
| `set_center(...)` | Show or hide `CENTER` and point its URL or file at the card. |
| `set_headline(text)` | Set the text on input `HEADLINE`. |
| `set_name_bar(...)` | Set text on `NAME_BOT1` / `NAME_BOT2`. |
| `duck_music(db)` | Set volume on input `BED`. |
| `get_program_state` | Current scene name + media time remaining on `HOST_WIDE`. |

If a named scene or input is missing, the call fails loudly and the harness goes to `hold`. It does not invent a scene.

**Reconnect.** If the port drops: retry with backoff (1s, 2s, 4s, cap 8s). OBS keeps playing what is already on air. A stale layout is allowed. A dead process is not. After 30s of no connection, exit with the log intact.

---

## 5. OBS scene contract

Built by hand. Exported and checked into `scenes/README.md` as a name list (not a binary we cannot review). The check in M0 is “these names exist and the split shares a play time.”

**Scenes (layouts)**

| Scene | Must contain |
| :---- | :---- |
| `wide` | `HOST_WIDE` full frame; `HEADLINE`; name bars; clock/LIVE if you want them. |
| `split` | Two scene items of `HOST_WIDE` (left crop, right crop); `CENTER` on the join; `HEADLINE`; name bars. |
| `solo_l` | Left crop of `HOST_WIDE`, larger. |
| `solo_r` | Right crop of `HOST_WIDE`, larger. |
| `card_full` | `CENTER` full frame. `HOST_WIDE` may be hidden but its audio still in the mixer. |
| `hold` | `CENTER` or a still; tickers/bed visible. No host face as the only picture. |

**Inputs (sources)**

| Name | Kind | Notes |
| :---- | :---- | :---- |
| `HOST_WIDE` | Media / ffmpeg source | The one paid window. The only file `play_clip` may change. |
| `CENTER` | Browser or image | The post card. |
| `HEADLINE` | Text | |
| `NAME_BOT1` `NAME_BOT2` | Text | |
| `HL_BOT1` `HL_BOT2` | Color or border | Speaking highlight. |
| `BED` | Audio | Music. |

**Crop-sync check (M0, on a real OBS)**

1. Point `HOST_WIDE` at `assets/clips/sync_check.mp4` (a file with a visible timecode or a hard cut at 2.5s).
2. Switch to `split`.
3. Play.
4. Pass: both halves hit the cut at the same time, by eye. Fail: they drift. **Fail means stop.** Do not add more layouts. Write the result into §12.

`sync_check.mp4` can be any 5s file we already have. It does not have to be the hosts.

---

## 6. Data contracts

### 6.1 Show list — `rundown.yaml`

```yaml
show:
  name: Runtime
  target_len_s: 90
  mode: rehearse

posts_file: posts.json
script_file: script.jsonl
clip_pool: assets/clips/

segments:
  - id: timeline_react_1
    kind: talk
    target_len_s: 90
    layout_plan: [wide, split, split, wide, split]
    package:
      item_id: "1950123999999999999"
      question: "If you have no thesis, is the move even information?"
      framing: "Fear as weather."
      angles: ["a ticker that shrugs is still a ticker"]
      chyron: "A MOVE WITHOUT A THESIS"
      center: {kind: tweet_card, post_id: "1950123999999999999"}
      spend_policy: normal
```

One segment is enough. A bumper segment is allowed but not required for done.

### 6.2 Script — `script.jsonl`

One thought per line. The harness pops the next line when the written-ahead slot is below 2.

```json
{"speaker": "BOT1", "text": "The tape is a rumor with a timestamp.", "thought_open": false}
{"speaker": "BOT2", "text": "Then give me the timestamp.", "thought_open": false}
```

When the file ends, `next_line` is null. The director then stops submitting and finishes on hold.

### 6.3 Posts — `posts.json`

```json
{
  "posts": [
    {
      "id": "1950123999999999999",
      "author": "marketsguy",
      "text": "the vix just did a thing and nobody knows why",
      "url": "https://example.invalid/status/1950123999999999999"
    }
  ]
}
```

The center card is allowed to show this text. How it is drawn (HTML file vs OBS text) is an implementation detail as long as `set_center` can show and hide it.

### 6.4 Snapshot the director sees

Built by the harness from `ProgramState` plus its own queues. The director does not talk to OBS.

```json
{
  "t": 12.4,
  "on_air": {
    "layout": "split",
    "take": 2,
    "duration_s": 5,
    "ends_at": 15.0,
    "speaker": "BOT2"
  },
  "ready": [],
  "cooking": {"take": 3, "submitted_at": 10.1},
  "chain_ready": false,
  "next_line": {
    "speaker": "BOT1",
    "text": "Fear has a ticker now, and it shrugs."
  },
  "spend_usd": 0.0,
  "spend_cap_usd": 20.0,
  "holds_recent": 0,
  "flags": {"hold": false, "panic": false},
  "segment": {
    "layout_plan": ["wide", "split", "split", "wide", "split"],
    "center": {"kind": "tweet_card", "post_id": "1950123999999999999"},
    "chyron": "A MOVE WITHOUT A THESIS",
    "spend_policy": "normal"
  }
}
```

In rehearse, `spend_usd` stays `0.0`. `chain_ready` is true when nothing is cooking and we have a last-frame path *or* (this slice) the stub has finished the previous take. The stub always “has a last frame” once a take is ready. Cold start: `chain_ready` is true so take 1 can submit.

### 6.5 Beat the director emits

```json
{
  "at": 15.0,
  "layout": "card_full",
  "host_source": null,
  "speaking": null,
  "center": {"kind": "tweet_card", "post_id": "1950123999999999999"},
  "chyron": "A MOVE WITHOUT A THESIS",
  "submit": null,
  "why": "take 3 is still cooking; put the post up"
}
```

When a host clip should play:

```json
{
  "at": 15.4,
  "layout": "split",
  "host_source": "ready:3",
  "speaking": "BOT1",
  "center": {"kind": "tweet_card", "post_id": "1950123999999999999"},
  "chyron": "A MOVE WITHOUT A THESIS",
  "submit": {
    "take": 4,
    "line": "Fear has a ticker now, and it shrugs.",
    "speaker": "BOT1",
    "anchor": "stub"
  },
  "why": "ready clip exists; stub is free; under cap"
}
```

`submit` is null when: panic, hold flag, `spend_policy` is `stop`, no `next_line`, or a take is already cooking (depth 1). The director never writes `line`. It copies `next_line`.

### 6.6 Log row — `out/takes.jsonl`

```json
{
  "take": 3,
  "line": "Then give me the timestamp.",
  "speaker": "BOT2",
  "clip": "out/ready/003.mp4",
  "status": "ready",
  "layout_on_air": "split",
  "t_submit": 10.1,
  "t_ready": 14.8,
  "t_on_air": 15.4,
  "delay_s": 4.7,
  "forced_late": false,
  "cost_usd": 0.0
}
```

`status`: `ready` | `late` | `held` | `killed` | `skipped_end`.  
This file is the proof. Timing tests read it.

---

## 7. Director rules (v1)

Pure function. No I/O. Same snapshot always yields the same beat.

Use the next unused name in `layout_plan` when a host clip goes on air. If the plan is exhausted, repeat the last name. Never pick `hold` from the plan; hold is only for failure or flags.

**Order. First match wins.**

1. **Panic.** Layout `hold`. `host_source` null. `submit` null. `why`: panic.
2. **Hold flag.** Layout `hold`. Do not submit. If a ready clip exists, leave it in the queue.
3. **Ready clip exists.**  
   - `host_source` = that clip.  
   - `layout` = next plan name (if it is a host layout).  
   - `speaking` = that clip’s speaker.  
   - `center` and `chyron` from the segment.  
   - `submit` = next line if all of: no take cooking, `next_line` is not null, `spend_policy` is `normal`, not panic/hold.  
   - Else `submit` null.
4. **No ready clip, a take is cooking.**  
   - Layout `card_full` if `center.kind` is not `none`, else `hold`.  
   - `submit` null.  
   - `why`: waiting on cooking.
5. **No ready clip, nothing cooking.**  
   - If `next_line` exists and `spend_policy` is `normal`: layout as in (4), `submit` the next line (cold start or after a hole).  
   - Else: layout `hold`, `submit` null, `why`: script ended or stop.

The harness executes the beat, then:

- `set_layout`, `set_headline`, `set_center`, `set_speaking`, `duck_music` (−6 dB if speaking is set, 0 dB if not).
- If `host_source`: `play_clip` on that path, mark the take on air, pop it from ready.
- If `submit`: call the stub, mark cooking, consume that thought from written-ahead, refill from `script.jsonl`.

**Do not** call the player from `director.py`.

---

## 8. Stub performer

Input: the `submit` object.  
Work: wait `delay_s`, then copy the next file from `assets/clips/` (round-robin) to `out/ready/{take:03d}.mp4`, append a log row, clear cooking.

`delay_s` comes from config:

```yaml
stub:
  delay_s: 4.0
  delay_jitter_s: 0.5
  forced_late_takes: [3]
  forced_late_delay_s: 8.0
```

Take numbers in `forced_late_takes` use `forced_late_delay_s` instead. That is how hold is proven on purpose. Default: take 3 is late so a 5s clip on air runs out before take 3 lands.

The stub never calls fal. It never reads `FAL_KEY`. If that env var is set, ignore it.

Clip pool: at least three 5-second mp4s. Content can be anything visible (color bars, old tests). Duration must be readable (ffprobe) and stored on the log row.

---

## 9. Timing

Short loop wakes when `on_air.ends_at` is reached, or every 200 ms if nothing is on air, or when the stub marks a take ready (so we do not sit on a card until the next 200 ms poll after a late land).

| Step | Budget |
| :---- | :---- |
| Director | < 5 ms (function) |
| Player calls | < 100 ms on localhost |
| Stub delay | Config. Default ~4s so a 5s clip has slack, except forced-late takes |
| Ready depth | 0 or 1. Never start a second cooking take |

Cold start: nothing on air. Rule 5 submits take 1, picture is `card_full` or `hold` until the stub lands. That first wait is supposed to look like a show, not a host.

---

## 10. Errors

| Failure | Response |
| :---- | :---- |
| Stub later than the cut | Rule 4. Card or hold. When the file lands, next wake plays it. |
| Script file empty | No submit. End on hold after the last ready clip. Exit 0. |
| Player not connected at start | Do not start the loop. Exit 2. |
| Player drops mid-show | Reconnect. Keep the log. If 30s down, exit 3. |
| `play_clip` file missing | Treat as late. Hold. Log `status: killed`. Do not crash. |
| Named scene missing | Hold. Log. Exit 4 after the current picture if we cannot switch. |
| Panic flag | Rule 1. Finish nothing new. Exit 0 when current picture ends. |
| Tests cannot see OBS | Fine. Fake player tests must still pass. |

---

## 11. Tests

Two layers. Do not skip the first.

### 11.1 Automated (fake player, no OBS, $0)

Each item is a pytest. The fake player exposes `advance(seconds)` and a recorded list of calls.

| ID | Test | Pass |
| :---- | :---- | :---- |
| T1 | Director rule 4: cooking, no ready → `card_full`, `submit` null | Exact beat |
| T2 | Director rule 3: one ready, next line, not cooking → play ready, submit next | Exact beat |
| T3 | Director rule 1: panic → `hold`, no submit | Exact beat |
| T4 | Director does not write a new line; it copies `next_line.text` | Assertion on beat.submit.line |
| T5 | Cold start: no ready, no cooking, next line exists → submit take 1, layout card/hold | Exact beat |
| T6 | Script ended, nothing ready, nothing cooking → hold, no submit | Exact beat |
| T7 | Loop: stub delay 4s, clip 5s, three takes → no hold in the log | `held` count 0 |
| T8 | Loop: take 3 forced to 8s delay → at least one `card_full` or `hold` beat, then take 3 still airs | Log shows late then ready |
| T9 | Written-ahead stays at 2 until the script runs out | Slot length |
| T10 | Player interface: harness never imports `player_obs` from `director.py` | Import linter or grep in CI |

T7–T9 run `run.py` against `FakePlayer` + stub in-process (no socket).

### 11.2 On the desk (real OBS, $0)

| ID | Check | Pass |
| :---- | :---- | :---- |
| D0 | Crop-sync (§5) | Both halves of `split` share the cut |
| D1 | Hand drive: switch `wide` → `split` → `hold`, `play_clip`, set headline | Visible, no new scenes created |
| D2 | `run.py --mode rehearse` for 90s with OBS as player | Done-criteria in §1 |
| D3 | Kill the remote-control port for 3s mid-run, then restore | Reconnect; picture never goes black from our side |

D2 is the acceptance run. Record `out/takes.jsonl` from that run in the notes when it first passes.

---

## 12. Milestones

| # | Deliverable | Gate |
| :---- | :---- | :---- |
| **H0** | `scenes/README.md` name list. OBS collection built by hand. D0 crop-sync. | Split shares a play time. **Stop if not.** |
| **H1** | `Player` + `FakePlayer` + `director.py`. T1–T6 green. | Function is the director. |
| **H2** | Stub + short loop + log. T7–T10 green. | Hold fires on purpose in fake time. |
| **H3** | `player_obs.py` + D1. Hand-drivable. | Scenes switch; no scene created. |
| **H4** | Full `rehearse` on the desk. D2, D3. | §1 done-criteria. |

Do not start a fal performer, a writer model, or a producer model before H4.

H0 can proceed in parallel with H1–H2. H3 needs H0.

---

## 13. Disk layout

```
harness/
  config.yaml
  run.py
  director.py
  player.py
  player_obs.py
  player_fake.py
  performer_stub.py
  rundown.yaml
  script.jsonl
  posts.json
  scenes/README.md
  assets/clips/           # ≥3 mp4s, plus sync_check.mp4
  out/ready/
  out/takes.jsonl
  tests/test_director.py
  tests/test_loop.py
```

**`config.yaml` (excerpt)**

```yaml
mode: rehearse
player: fake          # fake | obs
obs:
  host: 127.0.0.1
  port: 4455
  password_env: OBS_WEBSOCKET_PASSWORD
stub:
  delay_s: 4.0
  delay_jitter_s: 0.5
  forced_late_takes: [3]
  forced_late_delay_s: 8.0
spend:
  cap_usd: 20.0       # unused in rehearse; still present
```

Secrets only from the environment. Repo contains none.

---

## 14. Cost

**$0.** No fal. No writer API. If a future change imports a fal client in this slice, that is a bug.

The two-host live budget and the 1 Sep promo do not apply here. They apply when a later TDD turns `live` on.

---

## 15. Risks

| Risk | What we do |
| :---- | :---- |
| Split crops drift (D0 fails) | Stop. The show may fall back to `wide` only. Do not invent a second media source to “fix” sync. |
| OBS `play_clip` gaps or restarts badly | Log it. If D2 fails for gaps, the next decision is “different OBS settings” or “a second player backend,” not a fork. |
| Media time remaining is wrong | Prefer “file duration + start time” on our side if OBS time is jumpy. The harness clock can own `ends_at`. |
| Someone adds fal to “just try” | Refuse in `run.py` if `mode != rehearse` in this slice. |

---

## 16. What the next TDD is (not this one)

After H4:

1. **Live performer** — fal, last-frame PNG, spend cap, the older one-host measurements (verbatim, drift) if they are still unproven.
2. **Writer agent** — same thought schema, model instead of `script.jsonl`.
3. **Producer agent** — same package schema, model instead of the block in `rundown.yaml`.

Each keeps the player interface and the director function. If those change, this TDD was wrong.

---

## 17. Open questions for review

1. Python + asyncio on the desk is still the language. Agree?
2. Fake-player tests are the merge gate; OBS checks are on the desk. Agree?
3. Take 3 is the forced-late take. Agree, or pick another?
4. Tickers and stings wait. Agree?
5. Crop-sync fail means stop, not “add a second source.” Agree?
