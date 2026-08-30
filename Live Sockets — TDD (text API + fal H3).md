# TDD — Live sockets (text API + fal H3)

**Status:** Draft for build · **Date:** 30 Aug 2026 · **Owner:** Jesse  
**Release:** Not public v1. Ships with the show, or as a later package that *depends on* the OBS harness. Do not fold this into `OBS Harness — TDD.md`.

**Depends on:** `OBS Harness — TDD.md` — player interface, director rules, stub performer, H4 done.  
**Parent:** `Agentic Live Streaming Harness — Plan.md`.  
**Show context:** `Desk Show — Two-Host Architecture & Harness.md` (prompt bible, last-frame chain). That file is not required to implement the sockets; it is required to assemble a Runtime prompt.

No code in this file.

---

## 0. What this is

The OBS harness already plays files and cuts layouts. This TDD adds the other two sockets so a person can run a *live* show:

| Socket | What they connect | Who pays |
| :---- | :---- | :---- |
| **Text** | Their own text-API account (OpenAI-shaped: URL, key, model name) | Them, to that vendor |
| **Video** | Their fal account, MiniMax H3 Max | Them, to fal |

The OBS socket is already specified. This file does not reopen it.

We do not create accounts. We do not OAuth through our servers. We do not proxy their calls. Keys stay on their machine.

**Must not change:** `Player`, `director.decide`, scene names, the short-loop wake rules. If live needs a new director rule, fix it in the OBS TDD first and bump that release.

---

## 1. Goals

After H4 of the OBS harness:

1. They can save a text key and a fal key on the machine and `check` that the text key works.
2. `rehearse` still uses the file script and the stub, even if keys are present. Cost $0.
3. `live` uses their text API to fill the same thought schema, and fal H3 Max to fill the same `submit` → ready-file path.
4. A spend cap can refuse the next fal call.
5. Secrets never appear in `takes.jsonl` or in a beat.

**Done when:** D5–D6 pass (one live take, then a second take chained on the first PNG) with a cap of $2 unless raised.

**Out of this TDD:** producer as a model, Twitch as our feature, a second video vendor, a second text request shape, storing keys on our servers.

---

## 2. Locked decisions

| Decision | Choice |
| :---- | :---- |
| Keys | Environment or a gitignored local file. Never the repo. |
| Text shape | OpenAI-compatible `POST {base_url}/chat/completions` only. |
| Video | fal `minimax/h3-max/image-to-video` only. |
| Writer | Live adapter implements the same `write_thought(...)` the file script already matches. |
| Performer | Fal adapter implements the same `start(submit)` the stub already matches. |
| Producer | Still a file. |
| First live cap | $2 unless Jesse raises it. |

---

## 3. Config

```yaml
mode: live                    # rehearse | live
player: obs                   # fake | obs  (from OBS TDD)

text:
  enabled: true
  kind: openai_compatible
  base_url_env: TEXT_BASE_URL
  api_key_env: TEXT_API_KEY
  model_env: TEXT_MODEL

video:
  enabled: true
  kind: fal_h3_max
  key_env: FAL_KEY
  endpoint: minimax/h3-max/image-to-video
  duration: 5
  resolution: 768p
  prompt_expansion_mode: balanced

spend:
  cap_usd: 20.0
  rate_768p_usd_per_s: 0.08
```

**Connect** is a local settings step (file or a one-page form that writes the env file): OBS password (already required), text URL + key + model, fal key.

**`check` probes**

| Probe | What we send | Pass |
| :---- | :---- | :---- |
| OBS | `get_program_state` | `connected: true` |
| Text | One chat call, `max_tokens` 8, prompt `reply with the word pong` | Body contains `pong` (case-insensitive) |
| Video | Key present and accepted. Paid clip only with `--probe-video` | HTTP 401 = fail |

Do not start `live` if text or fal config is missing.

---

## 4. Text socket — `Writer`

```
write_thought(package, script_so_far, next_speaker, thought_open) -> Thought
```

```json
{"speaker": "host_a", "text": "Fear has a ticker now, and it shrugs.", "thought_open": false, "angle_used": "a ticker that shrugs is still a ticker"}
```

Runtime may send `BOT1` / `BOT2` as speakers; the writer does not care. The harness maps show names to `host_a` / `host_b` before `set_speaking`.

**Live call:** one POST to `{base_url}/chat/completions`. System prompt = host voices + hard rules (JSON only, spoken text only, do not fetch posts, do not write to the clock). User payload = package + script so far + next speaker.

Why this shape: one adapter covers OpenAI, Groq, Together, OpenRouter, Fireworks, and any local server that pretends to be OpenAI.

**Must not:** see playhead time, spend, last-frame URLs, or OBS.

**Failure:** timeout 8s. Do not invent a line. After 3 failures, stop submitting and log `writer_down`. The OBS director already holds when `next_line` is missing.

---

## 5. Video socket — `Performer`

```
start(submit) -> None     # async; later the take appears in ready
```

When done: `out/ready/{take:03d}.mp4`, `out/frames/{take:03d}.png`, frame URL if uploaded, row in `out/takes.jsonl`.

**Live steps (`performer_fal.py`):**

1. Refuse if the spend meter says the next clip would cross the cap.
2. Build the prompt from the show bible (`studio.yaml` on Runtime) + who is speaking + the line in quotes. Do not improvise.
3. `fal.subscribe("minimax/h3-max/image-to-video", { prompt, image_url, duration, resolution, prompt_expansion_mode })`.
4. `image_url` = last take’s frame URL, or the hero still on take 1 and every re-anchor.
5. Download mp4. Extract last frame with ffmpeg as PNG (never JPEG). Upload PNG.
6. Log timings and `cost_usd` (requested duration × rate).

**Must not:** change the line. Pick a layout. Talk to OBS.

**Failure:** HTTP 422 → drop take, cost still counts, writer is asked again with `reissue: shorter, blander`, director holds. Never retry the same prompt. Other errors → retry once, then hold. 3 consecutive fails → graceful stop.

---

## 6. Spend meter

A function. Wraps every fal call.

- Adds `duration * rate` on submit.
- Refuses the next `start` when `spend_usd + next >= cap`.
- Rehearse: always $0.

---

## 7. Mode switch

| Mode | Writer | Performer |
| :---- | :---- | :---- |
| `rehearse` | Script file | Stub (OBS TDD) |
| `live` | Text adapter | Fal adapter |

`rehearse` ignores text/fal keys if present.  
`live` refuses to start if either socket is missing.

---

## 8. Tests

| ID | Test | Pass |
| :---- | :---- | :---- |
| S1 | Live mode without `TEXT_API_KEY` refuses to start | Exit ≠ 0, no fal call |
| S2 | Live mode without `FAL_KEY` refuses to start | Exit ≠ 0 |
| S3 | Rehearse with keys present still uses stub, cost 0 | No HTTP to fal |
| S4 | Writer adapter: mocked chat response → valid Thought | Schema |
| S5 | Writer adapter: timeout → no invented line | Slot unchanged |
| S6 | Fal adapter: mocked subscribe → file + PNG + log row | Paths exist |
| S7 | Fal adapter: mock 422 → status `dropped_422`, hold path | No retry of same prompt |
| S8 | Spend meter refuses when cap would break | No `start` |
| S9 | Secrets do not appear in `takes.jsonl` or beats | Grep |

On-desk (paid, small):

| ID | Check | Pass |
| :---- | :---- | :---- |
| L1 | `check` text probe with a real key | pong |
| L2 | One live take: their text API writes a line, fal returns 5s, OBS plays it | One log row, cost > 0 |
| L3 | Second take chains on the first PNG | `anchor: chain` |

L2–L3 cap at $2 for the first sitting unless raised.

---

## 9. Milestones

| # | Deliverable | Gate |
| :---- | :---- | :---- |
| **S0** | OBS harness H4 is done in its own package. | Do not start here first. |
| **S1** | Settings / env + `check`. Tests S1–S3, S9. | Live will not start half-plugged. |
| **S2** | Writer adapter. Tests S4–S5. | Their text account writes thoughts. |
| **S3** | Fal adapter + spend meter. Tests S6–S8, L2–L3. | Their fal account buys the clip. OBS already plays it. |

---

## 10. Disk layout (this package)

```
live-sockets/                 # or a Runtime package that depends on obs-harness
  writer.py
  writer_file.py
  writer_openai.py
  performer_fal.py
  spend.py
  secrets.env.example
  tests/test_writer_openai.py
  tests/test_performer_fal.py
  tests/test_spend.py
```

It imports `obs-harness` (player, director, stub, loop). It does not copy those files.

---

## 11. What we will not do

- Store keys on our servers.
- Offer “our OpenAI” or “our fal” as a billed feature.
- Use MiniMax’s own slow H3 as the live path.
- Add a second video vendor or a second text request shape in v1.
- Import the OBS player from the writer or the fal client.
- Change director rules in this package.

---

## 12. Open questions for review

1. Keys live on the user’s machine. We do not OAuth through our cloud. Agree?
2. Text is OpenAI-shaped so people can point at any compatible host. Agree?
3. Video is fal MiniMax H3 Max only in v1. Agree?
4. Producer stays a file until after S3. Agree?
5. First live sitting hard-caps at $2 unless raised. Agree?
6. This package is not in the public OBS harness release. Agree?
