# TDD — Desk Show MVP (one robot host, fal H3 Max)

**Status:** Draft for build · **Date:** 29 Aug 2026 · **Owner:** Jesse · **Author:** Claude (from Forge spec \+ 29 Aug Q\&A)

**Parent docs:** "Desk Show — H3 Max Spec \+ Review \+ Drift Plan" (Drive \+ project). This TDD covers only the confirmed first-build slice.

---

## 1\. Overview and goals

The MVP is a single Python program on Jesse's machine that runs a one-host live loop for 60+ seconds: a hosted open-source LLM writes each line, fal MiniMax H3 Max performs it as a 5s 768p talking-head clip of an original robot host, and a local player plays clips back-to-back while the next clip generates. Full-frame talking head in a window — no set compositing beyond the player, no cutout.

**The MVP proves or measures four things:**

1. **Play-while-generating works** — 60s of continuous playback with no stall, with the hold pattern demonstrated at least once on purpose.  
2. **Verbatim line delivery** — H3 Max speaks the exact line it is given (this is an assumption the whole show design rests on; it has never been tested).  
3. **Identity drift, characterized** — face drift across a last-frame chain vs re-anchored takes, and voice drift on raw audio across 8+ takes.  
4. **Real $/min** — measured, including retries and failed takes.

**Non-goals (explicitly out of MVP):** second host, tweet ticker, cutout/chroma-key, OBS, streaming to any platform, deployment, monetization, 15s clips, official MiniMax H3 on the live path.

**Locked decisions (29 Aug Q\&A):** Python on Jesse's machine (macOS/Linux; Windows via WSL). Live LLM writer from day one — an open-source distilled model chosen later by speed test, served by a hosted inference API behind an OpenAI-compatible interface. Local player watching the ready folder (no OBS). One original robot host, stylized/occluded mouth. H3's own audio kept raw AND passed through a fixed ffmpeg robot-effect chain behind a toggle. Budget cap \~$25; keys ready. fal promo pricing (50% off) ends 1 Sep 2026 — build this weekend halves every number below.

---

## 2\. System architecture

Six components, one process (asyncio), one machine. A clip queue with a playhead — never a stream. The **only state that crosses turns** is the line as text plus the host's last-frame PNG URL.

**Data flow:** topic seeds (config) → **WRITER** (OpenAI-compatible client → hosted endpoint; line N+1 drafts while N generates) → line as plain text (≤ \~12 words, ends on a period) → **GENERATOR** (fal `minimax/h3-max/image-to-video`, `image_url` \= last-frame PNG or hero still) → mp4 → **POST** (ffmpeg last-frame PNG extract → fal CDN upload; audio kept raw \+ robot effect chain behind toggle) → ready mp4 \+ manifest row (`takes.jsonl`) → **READY QUEUE** (folder) → **PLAYHEAD** (mpv `--keep-open`; freeze \= hold). The **SPEND METER** wraps every fal call and hard-stops the loop at the cap.

**Writer** — async client against any OpenAI-compatible chat endpoint (`WRITER_BASE_URL`, `WRITER_MODEL`, `WRITER_API_KEY` in config/env). Model is deliberately unpinned: Jesse speed-tests distilled open models and changes two config lines, zero code. System prompt carries the host persona and hard output rules (one spoken line only, ≤ 12 words, ends on a period, no stage directions). Writer runs **two beats ahead** of the playhead.

**Generator** — `fal_client` (async) calling `minimax/h3-max/image-to-video` with: `prompt` \= performance direction \+ the exact quoted line, `image_url` \= current anchor frame, `duration: 5`, `resolution: 768p`, `prompt_expansion_mode: "balanced"`. `FAL_KEY` from env only. Safety checker stays on.

**Post** — two ffmpeg jobs per take. Last frame: `ffmpeg -sseof -0.1 -i take.mp4 -frames:v 1 -update 1 frame.png` (PNG, never JPEG — recompression compounds across the chain), uploaded via `fal_client.upload_file()` to fal's CDN (no S3 to stand up; that URL is the next take's `image_url`). Audio: the raw track is always kept; when `voice_effect: on`, a second mp4 is written with the fixed robot filtergraph (§6) and *that* file goes to the ready queue.

**Ready queue** — `out/ready/` holding numbered mp4s plus `takes.jsonl`, one row per take (§3). Target depth 1: one clip ready, one generating.

**Playhead** — `mpv --idle=yes --keep-open=yes --input-ipc-server=/tmp/deskshow.sock`; the loop appends each ready clip via IPC (`loadfile <path> append-play`). `--keep-open` gives the hold pattern for free: when the playlist runs dry, mpv freezes on the last frame until the next append. No custom player code.

**Spend meter** — wraps every fal call; accumulates billed output-seconds × rate from config; refuses to submit past `spend_cap_usd` (default 20, leaving margin under the $25 budget) and logs cumulative cost per take into the manifest.

---

## 3\. Interfaces and data contracts

**Writer request/response.** Input: persona system prompt \+ rolling transcript of the last N lines \+ a topic seed. Output: one line of dialogue, plain text. Latency budget ≤ 1.5s (hosted inference on a distilled model should sit well under 1s; the two-beats-ahead rule makes even 3s survivable).

**fal call (fields used).** Request: `prompt`, `image_url`, `duration`, `resolution`, `prompt_expansion_mode`. Response: video URL (downloaded immediately to `out/raw/`), `timings.inference` (logged). Errors: HTTP 422 \= safety-checker rejection (handled, §5); anything else \= retry-once-then-hold.

**Manifest row** (`out/takes.jsonl`, one JSON object per take):

{"take": 7, "line": "The markets are simply numbers that argue.",

 "clip": "out/ready/007.mp4", "raw": "out/raw/007.mp4",

 "anchor": "chain",            // "chain" | "hero"

 "frame\_png": "out/frames/007.png", "frame\_url": "https://fal.../007.png",

 "voice\_effect": true,

 "t\_writer\_s": 0.6, "t\_queue\_s": 0.8, "t\_inference\_s": 2.6,

 "t\_download\_s": 0.7, "t\_post\_s": 0.4, "t\_total\_s": 5.1,

 "cost\_usd": 0.20, "cost\_cum\_usd": 1.40, "status": "ready"}   // ready | dropped\_422 | failed

This file **is** the measurement deliverable: $/min, timing distributions, and drift bookkeeping all come from it.

**Disk layout / repo skeleton:**

deskshow/

  config.yaml          \# persona, topic seeds, rates, caps, toggles, writer endpoint

  run\_live.py          \# the loop (asyncio)

  writer.py  generator.py  post.py  playhead.py  spend.py

  bake\_assets.py       \# one-time: hero still \+ pre-baked idle/hold take

  experiments/         \# day-one test scripts (§7)

  assets/hero.png  assets/hold.mp4

  out/raw/  out/ready/  out/frames/  out/takes.jsonl

**Config (excerpt):** `writer: {base_url, model, max_words: 12}` · `video: {duration: 5, resolution: 768p, expansion: balanced}` · `identity: {anchor_reset_every: 5, voice_effect: true}` · `spend: {rate_768p: 0.04, cap_usd: 20}` · `persona: |` (robot anchor character sheet) · `topics: [...]`. Secrets (`FAL_KEY`, `WRITER_API_KEY`) come from env, never config or repo.

---

## 4\. Timing model

Per-take serial cost against the 5.0s playback window (measured expectations, to be replaced with real numbers from the manifest):

| Step | Budget |
| :---- | :---- |
| Writer (off critical path — runs 2 beats ahead) | \~0.5–1.5s |
| Submit \+ queue wait | \~0.5–1.0s |
| Denoise (`timings.inference`, 5s @ 768p) | \~2.5–3.0s |
| Download mp4 | \~0.5–1.0s |
| Post: frame extract \+ PNG upload \+ audio chain | \~0.5–1.0s |
| **Critical path total (excl. writer)** | **\~4.0–6.0s** |

The window and the critical path are the same size — that is *why* the design needs a 1-clip ready buffer and never waits on the writer. Steady state: while take N plays, take N+1 is in flight, line N+2 is drafting. Generation of N+1 starts when N is **submitted**, not when it starts playing. First wait is hidden off-air by playing `assets/hold.mp4` (pre-baked 5s idle take) as playlist item zero. 15s takes are banned on the live path (render ≈ playback length → zero slack).

---

## 5\. Error handling

| Failure | Response |
| :---- | :---- |
| Safety 422 / checker dump | Drop the take (`status: dropped_422`), writer immediately reissues a shorter, blander line, playhead holds on freeze-frame. Show continues; cost of the dropped take still counted. |
| Slow generation (queue empty at the cut) | mpv `--keep-open` freeze \= hold pattern. Loop keeps going; no operator action. |
| Last-frame extract or upload fails | Fall back to `assets/hero.png` as next anchor (`anchor: "hero"`, accept the visual jump). Never stall the loop. |
| fal/API outage or repeated failures (3 consecutive) | Graceful stop: playhead finishes the queue, loop exits with the manifest intact. |
| Spend cap reached | Spend meter refuses the next submit; clean shutdown. Hard cap $20 default (margin under the $25 budget). |
| Writer endpoint slow/down | Two-beats-ahead buffer absorbs blips; on sustained failure, fall back to a canned line list bundled in config so the video pipeline test can finish. |

---

## 6\. Identity plan (face \+ voice)

**Host design requirements.** One original robot anchor — no resemblance to any existing character or person. Strong simple silhouette, chrome/matte head, and a **stylized or occluded mouth** (LED-waveform strip or slit visor): few facial degrees of freedom means drift reads as animation style, and the design stays compatible with a TTS-first fallback where lip sync stops mattering. Any residual glitchiness is diegetic — a slightly unstable android is a bit, not a bug.

**Hero still \+ hold assets** are baked offline by `bake_assets.py` before any live run (slow is fine off-air): generate the robot design as a still (fal image endpoint, or official MiniMax H3 character-reference for the matching idle clip), pick one canonical `assets/hero.png` (also the clip-0 anchor and the PiP window plate), and pre-generate one 5s idle/look-at-camera take as `assets/hold.mp4`.

**Face: chain \+ re-anchor policy.** Clip 0 anchors on `hero.png`. Each take then chains on the previous take's last-frame PNG, but every `anchor_reset_every` takes (default 5\) the anchor is **forced back to the hero still** — in the two-host show this reset hides inside cutaways; in the one-host MVP we accept the visible jump and measure it. Extract failure also resets to hero. PNG end to end.

**Voice: fixed effect chain behind a toggle.** Raw H3 audio is always archived (it is the drift measurement). When the toggle is on, the ready-queue copy is re-muxed through one unchanging filtergraph — starting point, to be tuned by ear once and then frozen:

ffmpeg \-i raw.mp4 \-c:v copy \-af \\

 "highpass=f=150,lowpass=f=3800,apulsator=hz=30:amount=0.65,\\

  acrusher=bits=10:mode=log:aa=0.6,alimiter=limit=0.9" treated.mp4

(≈ band-limit \+ 30Hz modulation \+ light bit-crush: the classic broadcast-robot treatment. The chain is the character's voice signature; underlying take-to-take timbre drift hides beneath it.) The writer prompt also pins a narrow vocal target: "flat robotic monotone, mid-pitch." If fal ships reference-to-video with audio refs mid-build, it does **not** enter the MVP — it is the first v2 item.

---

## 7\. Test plan (day-one experiments, each a script in `experiments/`)

| \# | Experiment | Method | Pass |
| :---- | :---- | :---- | :---- |
| E1 | Verbatim delivery | 8 takes, scripted lines; transcribe (local whisper-small or by ear) and diff | ≥ 7/8 word-accurate. **Fail → TTS-first fallback (§6/§10) before building more** |
| E2 | Voice drift (raw) | Same 8 takes, raw audio, blind listen A/B | A listener says all 8 are the same character; log a subjective 1–5 drift score |
| E3 | Voice effect masking | E2's takes through the §6 chain, same listen | Treated takes rated ≥ raw takes for consistency |
| E4 | Face drift | 8-take pure chain vs 8 takes with reset-every-5; ffmpeg contact sheet of frame 0 of each take | Re-anchored run visibly closer to hero; chain drift documented |
| E5 | 60s live run | `run_live.py`, 12 turns | No stall; ≥ 12 clips played; manifest complete |
| E6 | Forced hold | Kill one in-flight generation mid-run | Freeze-frame hold fires, loop recovers on its own |
| E7 | $/min | Compute from manifest incl. dropped takes | A real number, with retry overhead % |

E1–E4 share generation where possible (the same 8 chained takes serve E1, E2, E3 and half of E4).

---

## 8\. Milestones

**M0 — Assets** (\~1–2h): `bake_assets.py` produces `hero.png` \+ `hold.mp4`; robot design approved by eye. ✔ when both files exist and look like the same character.

**M1 — Single-take path** (\~2h): one command → writer line → fal call → mp4 \+ frame PNG \+ CDN URL \+ manifest row \+ treated audio. ✔ when a second run chains on the first's frame URL.

**M2 — Loop \+ queue \+ playhead** (\~3h): asyncio loop \+ mpv IPC; hold pattern works via `--keep-open`. ✔ when 4 takes play gaplessly, unattended.

**M3 — Proof \+ measurement** (\~2h): E1–E7 executed; numbers written back into this doc's §10. ✔ when the spec's done-criteria all hold: 60s no stall, hold fired on purpose, chain visible across 8+ takes, real $/min known — plus the two added criteria: verbatim delivery and voice consistency measured.

---

## 9\. Cost and budget (against the $25 cap)

At promo 768p ($0.04/s of output video; $0.20 per 5s take): E1–E4 ≈ 24 takes ≈ $4.80 · E5–E6 ≈ 14 takes ≈ $2.80 · M1/M2 shakeout ≈ 15 takes ≈ $3.00 · hero/hold baking ≈ $1–2. **Base ≈ $12; with a 1.8× retry/mess multiplier ≈ $21** — inside the $25 cap with the spend meter's hard stop at $20 (raise deliberately if needed). At list rates (from 1 Sep) everything doubles: same plan ≈ $42 — still cheap, but this weekend is literally half price. Writer-model tokens on a hosted distilled model are noise (\<$0.50).

---

## 10\. Risks and open items

- **E1 fails (non-verbatim delivery)** — the pivotal risk. Mitigation is designed in: switch to TTS-first (fixed stock voice, deterministic; the robot's waveform mouth makes lip sync irrelevant), mux TTS audio in Post. Writer and loop are untouched.  
- **fal ships reference-to-video mid-build** — do not chase it; finish the MVP measurements, adopt in v2 where its numbers can be compared against the chain's.  
- **Writer model unpinned** — deliberate; Jesse speed-tests distilled open models against the ≤1.5s budget and sets two config values.  
- **Promo expiry 1 Sep** — costs double after Monday; affects budget math only, not design.  
- **Results to be written into this doc after M3:** measured $/min, timing distribution, E1–E4 outcomes, and the go/no-go on raw-audio voice vs effect chain vs TTS-first.  
- **v2 backlog (in order):** second host \+ cutaway re-anchoring, tweet ticker (adversarial-input handling from the review applies), chroma-key cutout, OBS/compositor, reference-to-video.

