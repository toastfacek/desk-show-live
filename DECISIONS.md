# Decisions log — ambiguities resolved before build (29 Aug 2026)

Every choice the TDD/spec left open (or that Jesse's "use this as an OBS setup for a
streaming service" request re-opened), with the call made for the MVP build. Override any
of these by editing `config.yaml` — none require code changes unless noted.

## D1. OBS / streaming vs the TDD's "no OBS" non-goal

**Tension:** the TDD lists OBS and streaming as explicit non-goals; Jesse wants this to
become an OBS setup for a monetizable streaming service.

**Call:** the *loop* stays exactly the TDD's loop (no streaming code on the live path),
but the playhead is pluggable (`player:` in config):

- `mpv` (TDD default) — mpv `--keep-open` window; the hold pattern is free. **This is
  also the OBS path**: OBS window-captures the mpv window. Zero extra code, gapless.
- `folder` — the loop only maintains `out/ready/` plus a growing `playlist.ffconcat`;
  OBS's VLC/Media source (or any consumer) watches it. Use when mpv isn't wanted on the box.
- `none` — headless (tests, experiments, CI).

Full OBS scene + Twitch/YouTube setup and the monetization math live in `OBS.md`.
Streaming itself is carried by OBS, not by this program — which matches the spec's v2
ranking and keeps the MVP measurable this weekend.

## D2. Writer endpoint (deliberately unpinned in the TDD)

Config ships pointing at Groq (`https://api.groq.com/openai/v1`,
`llama-3.1-8b-instant`) purely as a working example of a fast hosted distilled model
behind an OpenAI-compatible interface. Change `writer.base_url` + `writer.model` after
speed-testing; `WRITER_API_KEY` from env only. Sustained writer failure falls back to
`writer.canned_lines` in config, per §5 of the TDD.

## D3. "Generation of N+1 starts when N is submitted" (§4, ambiguous)

Read literally this would mean overlapping generations (2 in flight), which doubles burn
and contradicts the stated steady state ("take N plays, N+1 in flight, N+2 drafting").

**Call:** at most **one generation in flight**; the pipeline is driven by generation
completion, never by playback events, and stops submitting when the ready queue already
holds `max_ready_depth` (default 2) unplayed clips. This gives the intended behavior —
the playhead never gates the pipeline — without double concurrency. `max_ready_depth`
is config if we ever want a deeper buffer.

## D4. Reissue-after-422 mechanics

The TDD says the writer "immediately reissues a shorter, blander line." **Call:** the
reissue bypasses the two-beats-ahead queue — it is a direct writer call with an explicit
reissue instruction (max words halved, "bland, safe, neutral"), so the queue's prefetched
lines are preserved for the following turns. If the reissue itself 422s, the take is
skipped entirely and the loop moves on (counts toward the 3-consecutive-failures stop).

## D5. Dry-run mode (not in the TDD; added)

`run_live.py --dry-run` replaces the fal call with a local ffmpeg-rendered 5s test-card
clip (line burned in, beep audio) plus a simulated latency. Zero spend. It exercises the
entire loop — writer, queue, post, manifest, playhead, hold pattern (E5/E6 logic) —
before a single billed take. This is how the loop was verified in CI-less conditions.

## D6. Anchor / identity knobs (TDD defaults kept)

- `anchor_reset_every: 5` — forced hero re-anchor; extract/upload failure also resets to
  hero (`anchor: "hero"` in the manifest). PNG end to end.
- Voice effect **on** by default; the §6 filtergraph is in config verbatim and should be
  tuned by ear once, then frozen. Raw audio always archived in `out/raw/` (it *is* the
  E2 measurement).

## D7. Spend

Rate `$0.04/s` (768p promo), hard cap `$20`. The meter **loads prior spend from
`out/takes.jsonl` on startup**, so repeated runs share one budget — the TDD didn't say;
this is the safe reading. Delete/rotate the manifest to reset the meter deliberately.
After 1 Sep set `spend.rate_768p: 0.08`.

## D8. E1 transcription

`experiments/e1_verbatim.py` uses `faster-whisper` (small) if installed; otherwise it
extracts the audio tracks and prints a by-ear checklist. Whisper is an optional
dependency, not in `requirements.txt`.

## D9. Monetization direction (context for D1, not MVP scope)

At list rates an hour of one-host 768p is ~$288 generation alone (~$430–580 with retry
multiplier). 24/7 is a ~$10k/day habit; the viable shapes are **scheduled short daily
live blocks + clipped VOD/shorts**, or private/sponsored segments. Decision deferred
until E7 gives the real $/min; nothing in the MVP binds it.

## D10. Layout

TDD's flat skeleton kept (repo root = `deskshow/`). One module added beyond the
skeleton: `core.py` (config load, manifest I/O, paths) shared by the loop and the
experiments. Tests in `tests/` (pytest), covering the spend meter, writer sanitation,
and a full dry-run loop smoke test.
