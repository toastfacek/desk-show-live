# TDD — OBS Harness

**Status:** Draft for build · **Date:** 30 Aug 2026 · **Owner:** Jesse  
**Release:** This file is the whole public v1. It can ship without the desk show, without a text vendor, and without fal.

**Parent:** `Agentic Live Streaming Harness — Plan.md` (why a clock sits beside OBS).  
**Not in this release:** `Live Sockets — TDD (text API + fal H3).md` — people plug in their own text and video accounts. That is a later product. Do not merge it into this repo cut.

The older `Desk Show MVP — TDD` is a one-host fal test with a simple player. Different slice. Do not mix it in.

No code in this file. After it is accepted, implementation follows these contracts.

---

## 0. What this release is

A small program that sits **next to stock OBS** and runs a live show from files: a show list, a script, and a folder of clips. It owns the clock. OBS owns the picture and the stream.

It is not a fork of OBS. It is not a new switcher. It does not call a language model. It does not buy video. It does not need anyone’s API key except the OBS remote-control password on localhost.

People who install the public cut get:

- a player interface and an OBS backend
- a director function (one snapshot in, one cut out)
- a stub that “cooks” the next clip by copying a local file after a delay
- a 90-second demo pack so they can press run without a show of their own

Runtime (the cartoon desk show) is one user of this program. It is not this program.

**License intent (when the repo is split):** MIT or Apache. Talking to OBS over the network does not make this GPL. Do not link `libobs` in this release.

---

## 1. Goals

A program on the same computer as OBS. It runs a 90-second show list in **rehearse** mode. A stub performer hands back existing video files after a fake delay. The director is a function.

**This release proves four things:**

1. **The clock owns the cut.** At each clip edge the harness asks the player what is on air, the director returns one instruction, the harness does that instruction. Nothing else is allowed to stall the cut.
2. **Hold is a layout, not a crash.** When the next file is late on purpose, the picture goes to `card_full` or `hold`, the headline stays, the music stays, and the show continues when the file lands.
3. **OBS is a backend, not the program.** All player calls go through a small interface. Tests of the director and the loop use a fake player. OBS is only required for the on-the-desk checks.
4. **The split shares one play time.** In OBS, `split` uses one media source twice, left crop and right crop. Both halves stay in sync. If this fails, stop and do not build more layouts on a lie.

**Done when (this is also “ready to release”):**

- 90 seconds run unattended with no dead air (no black frame, no frozen host face used as the hold).
- Hold fires at least once on purpose (stub delay longer than the clip).
- The log file has one row per take, including holds and the forced-late take.
- Director tests pass with the fake player (no OBS).
- Crop-sync check passes on a real OBS (or we write down that it failed and do not release a split layout).
- The tree has no fal client, no text-vendor client, and no secrets except the OBS password name in config.

**Out of this release**

Language models, fal, spend in real dollars, saving vendor API keys, Twitch as a feature we own (OBS can still stream; we do not wrap it), a custom switcher, creating or deleting OBS scenes from code, two video files on screen at once that must land together, chat driving the show.

A demo card that shows a fake post is in. A live Twitter feed is out.

---

## 2. Locked decisions

| Decision | Choice |
| :---- | :---- |
| Where it runs | The streaming machine, next to OBS. macOS or Linux first. Windows later if needed. |
| Language | Python 3.11+, one process, asyncio. |
| Player | OBS Studio 28+ (built-in remote-control port, protocol v5). Stock OBS. No fork, no plugin. |
| How we talk to OBS | A client library for that port (`obsws-python` or equal). Localhost. Password from the environment, never from the repo. |
| How the rest of the code sees the player | A `Player` interface (§4). OBS is one implementation. Tests use `FakePlayer`. |
| Director | Function. Snapshot in, one beat out. No model. |
| Show list / script | Files. The harness keeps two script lines ready. |
| Performer | Stub. Copies a canned mp4 into `out/ready/` after a jittered delay. Cost always $0. |
| Mode | `rehearse` only. Other mode names are refused. |
| Scenes | Built by hand once (or imported from the demo collection). Code may switch and fill. Code may not create, delete, or rename scenes. |
| Operator | A flag file or one key on a tiny local page: `hold`, `panic`. A full panel can wait. |

---

## 3. System architecture

One process. Two loops. The short loop is the product.

```
Show list (file)
  → slow loop: load the next segment package into memory
  → script slot: keep 2 thoughts from the script file

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

**Components**

| Name | Kind | Job |
| :---- | :---- | :---- |
| `run.py` | Loop | Reads config, runs both loops, writes the log, exits clean. |
| `director.py` | Function | Snapshot + show state → one beat. |
| `player.py` | Interface | The command list. |
| `player_obs.py` | Backend | Talks to OBS. Reconnects if the port drops. |
| `player_fake.py` | Backend | In-memory player for tests. Advances time when told. |
| `performer_stub.py` | Function | Fake delay, then a canned file. |
| `rundown.yaml` | Data | Demo show list. |
| `script.jsonl` | Data | Demo spoken lines, in order. |
| `posts.json` | Data | Demo card payload. |

No `fal` package. No OpenAI client. A CI grep fails the build if those appear.

---

## 4. The player interface

Every method the harness may call. No others in this release.

```
get_program_state() -> ProgramState
set_layout(name)                    # wide | split | solo_l | solo_r | card_full | hold
play_clip(path)                     # absolute path the player can open
set_speaking(host | null)           # host_a | host_b | null
set_center(kind, data)              # card | none
set_headline(text)
set_name_bar(host, name, handle)
duck_music(db)
```

Deferred: `set_ticker`, `play_sting`, `set_crop` as a live cut. Crop is set by hand in the scene.

The demo pack uses `host_a` / `host_b`. A show may map those to its own names in the rundown. The player only sees the two slots.

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
| `set_name_bar(...)` | Set text on `NAME_A` / `NAME_B`. |
| `duck_music(db)` | Set volume on input `BED`. |
| `get_program_state` | Current scene name + media time remaining on `HOST_WIDE`. |

If a named scene or input is missing, the call fails loudly and the harness goes to `hold`. It does not invent a scene.

**Reconnect.** If the port drops: retry with backoff (1s, 2s, 4s, cap 8s). OBS keeps playing what is already on air. A stale layout is allowed. A dead process is not. After 30s of no connection, exit with the log intact.

---

## 5. OBS scene contract

Built by hand. Names checked into `scenes/README.md` (a list we can review, not a binary). The H0 check is “these names exist and the split shares a play time.”

**Scenes (layouts)**

| Scene | Must contain |
| :---- | :---- |
| `wide` | `HOST_WIDE` full frame; `HEADLINE`; name bars. |
| `split` | Two scene items of `HOST_WIDE` (left crop, right crop); `CENTER` on the join; `HEADLINE`; name bars. |
| `solo_l` | Left crop of `HOST_WIDE`, larger. |
| `solo_r` | Right crop of `HOST_WIDE`, larger. |
| `card_full` | `CENTER` full frame. `HOST_WIDE` may be hidden but its audio still in the mixer. |
| `hold` | `CENTER` or a still; bed visible. No host face as the only picture. |

**Inputs (sources)**

| Name | Kind | Notes |
| :---- | :---- | :---- |
| `HOST_WIDE` | Media source | The one video window. The only file `play_clip` may change. |
| `CENTER` | Browser or image | The card. |
| `HEADLINE` | Text | |
| `NAME_A` `NAME_B` | Text | |
| `HL_A` `HL_B` | Color or border | Speaking highlight. |
| `BED` | Audio | Music. |

**Crop-sync check (H0, on a real OBS)**

1. Point `HOST_WIDE` at `assets/clips/sync_check.mp4` (a file with a visible timecode or a hard cut at 2.5s).
2. Switch to `split`.
3. Play.
4. Pass: both halves hit the cut at the same time, by eye. Fail: they drift. **Fail means stop.** Do not add more layouts. Write the result into §12.

`sync_check.mp4` can be any 5s file. It does not have to be a show.

---

## 6. Data contracts

### 6.1 Show list — `rundown.yaml`

The demo pack ships this. A later show replaces the files, not the program.

```yaml
show:
  name: demo
  target_len_s: 90
  mode: rehearse

posts_file: posts.json
script_file: script.jsonl
clip_pool: assets/clips/

segments:
  - id: demo_1
    kind: talk
    target_len_s: 90
    layout_plan: [wide, split, split, wide, split]
    package:
      item_id: "demo-1"
      chyron: "A MOVE WITHOUT A THESIS"
      center: {kind: card, id: "demo-1"}
      spend_policy: normal
```

One segment is enough. A bumper segment is allowed but not required for done.

### 6.2 Script — `script.jsonl`

One thought per line. The harness pops the next line when the ready slot is below 2.

```json
{"speaker": "host_a", "text": "The tape is a rumor with a timestamp.", "thought_open": false}
{"speaker": "host_b", "text": "Then give me the timestamp.", "thought_open": false}
```

When the file ends, `next_line` is null. The director then stops submitting and finishes on hold.

### 6.3 Card payload — `posts.json`

```json
{
  "posts": [
    {
      "id": "demo-1",
      "author": "example",
      "text": "the vix just did a thing and nobody knows why"
    }
  ]
}
```

`set_center` shows and hides this. HTML file vs OBS text is an implementation detail.

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
    "speaker": "host_b"
  },
  "ready": [],
  "cooking": {"take": 3, "submitted_at": 10.1},
  "chain_ready": false,
  "next_line": {
    "speaker": "host_a",
    "text": "Fear has a ticker now, and it shrugs."
  },
  "spend_usd": 0.0,
  "spend_cap_usd": 20.0,
  "holds_recent": 0,
  "flags": {"hold": false, "panic": false},
  "segment": {
    "layout_plan": ["wide", "split", "split", "wide", "split"],
    "center": {"kind": "card", "id": "demo-1"},
    "chyron": "A MOVE WITHOUT A THESIS",
    "spend_policy": "normal"
  }
}
```

`spend_usd` stays `0.0`. `chain_ready` is true when nothing is cooking and the stub has finished the previous take (or on cold start, so take 1 can submit). The field stays so a later video backend can mean “last frame exists” without changing the director.

### 6.5 Beat the director emits

```json
{
  "at": 15.0,
  "layout": "card_full",
  "host_source": null,
  "speaking": null,
  "center": {"kind": "card", "id": "demo-1"},
  "chyron": "A MOVE WITHOUT A THESIS",
  "submit": null,
  "why": "take 3 is still cooking; put the card up"
}
```

When a clip should play:

```json
{
  "at": 15.4,
  "layout": "split",
  "host_source": "ready:3",
  "speaking": "host_a",
  "center": {"kind": "card", "id": "demo-1"},
  "chyron": "A MOVE WITHOUT A THESIS",
  "submit": {
    "take": 4,
    "line": "Fear has a ticker now, and it shrugs.",
    "speaker": "host_a",
    "anchor": "stub"
  },
  "why": "ready clip exists; stub is free"
}
```

`submit` is null when: panic, hold flag, `spend_policy` is `stop`, no `next_line`, or a take is already cooking (depth 1). The director never writes `line`. It copies `next_line`.

### 6.6 Log row — `out/takes.jsonl`

```json
{
  "take": 3,
  "line": "Then give me the timestamp.",
  "speaker": "host_b",
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
- If `submit`: call the stub, mark cooking, consume that thought from the script slot, refill from `script.jsonl`.

**Do not** call the player from `director.py`.

---

## 8. Stub performer

Input: the `submit` object.  
Work: wait `delay_s`, then copy the next file from `assets/clips/` (round-robin) to `out/ready/{take:03d}.mp4`, append a log row, clear cooking.

```yaml
stub:
  delay_s: 4.0
  delay_jitter_s: 0.5
  forced_late_takes: [3]
  forced_late_delay_s: 8.0
```

Take numbers in `forced_late_takes` use `forced_late_delay_s`. That is how hold is proven on purpose. Default: take 3 is late so a 5s clip on air runs out before take 3 lands.

The stub never opens a network connection except OBS (and OBS is the player, not the stub). It never reads `FAL_KEY` or `TEXT_API_KEY`. If those env vars are set, ignore them.

Clip pool: at least three 5-second mp4s. Content can be anything visible. Duration must be readable (ffprobe) and stored on the log row.

---

## 9. Timing

Short loop wakes when `on_air.ends_at` is reached, or every 200 ms if nothing is on air, or when the stub marks a take ready.

| Step | Budget |
| :---- | :---- |
| Director | < 5 ms (function) |
| Player calls | < 100 ms on localhost |
| Stub delay | Config. Default ~4s so a 5s clip has slack, except forced-late takes |
| Ready depth | 0 or 1. Never start a second cooking take |

Cold start: nothing on air. Rule 5 submits take 1, picture is `card_full` or `hold` until the stub lands.

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
| T9 | Script slot stays at 2 until the file runs out | Slot length |
| T10 | `director.py` never imports `player_obs` | Import linter or grep in CI |
| T11 | Repo / this package has no fal or OpenAI client import | Grep in CI |

T7–T9 run `run.py` against `FakePlayer` + stub in-process (no socket).

### 11.2 On the desk (real OBS, $0)

| ID | Check | Pass |
| :---- | :---- | :---- |
| D0 | Crop-sync (§5) | Both halves of `split` share the cut |
| D1 | Hand drive: switch `wide` → `split` → `hold`, `play_clip`, set headline | Visible, no new scenes created |
| D2 | `run.py` for 90s with OBS as player | Done-criteria in §1 |
| D3 | Kill the remote-control port for 3s mid-run, then restore | Reconnect; picture never goes black from our side |

D2 is the acceptance run and the release run. Keep that `out/takes.jsonl`.

---

## 12. Milestones

| # | Deliverable | Gate |
| :---- | :---- | :---- |
| **H0** | `scenes/README.md` name list. OBS collection built by hand. D0 crop-sync. | Split shares a play time. **Stop if not.** |
| **H1** | `Player` + `FakePlayer` + `director.py`. T1–T6 green. | Function is the director. |
| **H2** | Stub + short loop + log. T7–T11 green. | Hold fires on purpose in fake time. No vendor clients. |
| **H3** | `player_obs.py` + D1. Hand-drivable. | Scenes switch; no scene created. |
| **H4** | Full demo on the desk. D2, D3. | §1 done-criteria. **This is the public v1.** |

H0 can proceed in parallel with H1–H2. H3 needs H0.

Do not add a text vendor or fal in this tree. That work has its own TDD and should live in a different package when we split repos.

---

## 13. Disk layout

```
obs-harness/
  README.md
  LICENSE
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
  tests/test_no_vendor_clients.py
```

Until the repo is split, this tree may live under `harness/` in `desk-show-live`. The names and the “no vendor clients” grep still apply.

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
```

The only secret is the OBS password, from the environment. Repo contains none.

---

## 14. Cost

**$0.** No video API. No text API. Importing a fal or OpenAI client in this package is a bug (T11).

---

## 15. Risks

| Risk | What we do |
| :---- | :---- |
| Split crops drift (D0 fails) | Stop. Ship `wide` only, or do not ship split. Do not add a second media source to “fix” sync. |
| OBS `play_clip` gaps or restarts badly | Log it. Next decision is OBS settings or a second player backend, not a fork. |
| Media time remaining is wrong | Prefer “file duration + start time” on our side if OBS time is jumpy. The harness clock can own `ends_at`. |
| Show-specific code creeps in | Demo pack only. Host voices, fal, and feed ingest do not land here. |

---

## 16. What is not in this TDD

How people connect a text API or fal is specified in `Live Sockets — TDD (text API + fal H3).md`. That document must not change the player interface or the director rules. If it needs to, this TDD was wrong.

---

## 17. Open questions for review

1. This file is the public v1. Agree to keep text/fal out of this package?
2. Python + asyncio on the desk is the language. Agree?
3. Fake-player tests are the merge gate; OBS checks are on the desk. Agree?
4. Take 3 is the forced-late take. Agree, or pick another?
5. Tickers and stings wait. Agree?
6. Crop-sync fail means stop, not “add a second source.” Agree?
7. Demo hosts are `host_a` / `host_b` (a show maps its own names). Agree?
8. License when we split the repo: MIT, unless you prefer Apache-2.0.
