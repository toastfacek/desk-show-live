# Runtime live flight check

Learnings from the first paid OBS live on this box (`live-20260901T155458Z`)
and the programme fixes that followed. Read this before the next `live` run.
The operator command sheet is [README.md](README.md).

Record only. `stream.enabled` stays false. Preflight refuses if OBS is already
streaming. Do not write `assets/broadcast/` until the graphics spec is relocked.

## What the check is

A 90s two-host H3 Max desk show through stock OBS:

- Generated picture is one **1344×768** two-shot (`HOST_WIDE`).
- 1080 furniture is deterministic (OBS / HTML). Fal never sees program-out.
- Paid generation uses **H3 baked-in speech**. Do not mix TTS with H3 audio.
- Overlay CG is the design-preview 3-column cut (two host wells + centre POST).
- Default on-air layout after cold start is **`split`**. Stay there while the
  next take cooks.

Named shows stay in research. They never enter Writer, HostMind, or H3 prompts.

## Flight that taught this

| | |
| :-- | :-- |
| Flight | `live-20260901T155458Z` |
| Work | `out/live-work/live-20260901T155458Z/` |
| Evidence | `out/flights/live-20260901T155458Z/` |
| OBS rec | `out/obs-recordings/2026-09-01 15-54-58.mkv` (~90.8s) |
| Spend | 10 fal submissions, $4.00 reserved of $8.00 |
| Aired | 8 takes (2 and 4 failed on fal). Writer stayed on BOT1. |

Automated `verify-flight` was **F-FAIL**: it wants 10 aired and both hosts.
Overlapping fal is intended. The harness keeps up to four H3 jobs in flight.
A speaker change or reanchor is a hero take and can start while another job
cooks. Same-speaker chain still waits for that host's last frame. The two
wells are crops of one two-shot; the ready buffer is a queue of those
two-shots, not two generators.

The first programme recording looked wrong in three ways that are easy to
misread: silent audio, cameras fading in and out, hosts pinned to the sides
of the wells. None of those were fal composition. They were this box's
`ffmpeg_source`, OBS Fade + `card_full`, and a hard 50/50 crop.

## Picture path

```
hero or previous last-frame URL
        → fal minimax/h3-max/image-to-video
        → ready/{take}.mp4          (evidence; Constrained Baseline)
        → prepare_obs_clip()
        → ready/{take}.obs.mp4      (programme; High@3.2, yuv420p, AAC)
        → HOST_WIDE local_file      (absolute path; OBS cwd is /workspace)
```

`play_clip` must send an absolute file. A relative `out/live-work/...` path is
resolved from OBS's cwd (`/workspace`), not from `runtime-flight/`, so the
source ends ENDED with empty wells.

Persist/chain uses the locked hero or the previous take's last-frame URL from
the H3 clip. The wash and overlay are OBS layers only. If you send program-out
back into fal you will bake CG and dither into the next take.

## Learnings

### 1. This box paints Constrained Baseline black and silent

Fal ready files are valid media: 1344×768, ~7.5 Mbps, Constrained Baseline,
AAC 32 kHz stereo. `ffmpeg_source` on this OBS (32.2.0, `DISPLAY=:1`,
`BrowserHWAccel=false`) paints them **black** and mixes **digital silence**.

`prepare_obs_clip()` remuxes a sibling `{stem}.obs.mp4` (libx264 High, yuv420p,
AAC). Evidence keeps the original. `ObsPlayer.play_clip` points `HOST_WIDE` at
the remux.

Proof from the first flight:

| File | Picture | Audio (`volumedetect`) |
| :-- | :-- | :-- |
| `ready/001.mp4` (fal) | Fine in ffplay | mean −19.3 dB |
| `15-54-58.mkv` (live, fal files on air) | Wells black / empty | AAC track, mean **−91 dB** |
| `16-02-38.mkv` (same takes, remuxed) | Picture in wells | mean −19.5 dB, peak −2.6 dB |

A walkthrough encoded with `-an` is silent by encode. That is not proof OBS
had no audio. Always `ffprobe` the mkv and run `volumedetect` before blaming
the mixer.

`HOST_WIDE` must stay unmuted, on the recording tracks, `close_when_inactive`
false, `clear_on_media_end` false. `play_clip` sets those on every take.

### 2. Cameras "fade" when HOST_WIDE leaves the scene

The two wells are transparent holes in the overlay. Empty well = dither wash.

Three things stacked on the first flight:

1. OBS scene transition was **Fade 300ms** (default). Cut exists; use it.
   Do not send `SetCurrentSceneTransitionDuration` 0 — OBS 402s (minimum 50ms)
   and Cut is a fixed transition anyway.
2. Director sent **`card_full` while the next take cooked**. `card_full` hides
   `HOST_WIDE`. Wells went to wash, then Fade brought the cameras back. That
   is the periodic blink.
3. `HOST_WIDE` **looped**. A ~5.18s take that stays on screen restarts, or
   flashes if the source clears at end-of-file.

Now:

- Scene transition is **Cut**.
- While cooking with no ready clip, hold the **last host layout** (usually
  `split`). Cold start still uses `card_full`. Programme end still uses `hold`.
- `looping` is false. Last frame holds until the next `play_clip`.
- `restart_on_activate` is false. `play_clip` still issues an explicit
  RESTART after pointing at a new file. The wait beat stays on `split`;
  re-entering that scene used to replay the finished take — speech, then
  silence, then the same line again, then silence.
- `set_layout` is a no-op when the program scene is already the target.
- Default `layout_plan` is `["split"]`. The overlay follows `card.json`
  `layout` (and preview `layout.json`): nametags hide with the missing
  host; solos widen the tweet well into the empty column; `card_full` /
  `hold` drop both nametags and stretch the card across the well band.
  `wide` is still a full-canvas two-shot under the 3-column CG.
  `wide → split → solo_l → solo_r` on the first flight was the rundown
  cycling, not a speaker cut.

Name plates follow layout, not speaking. Overlay speaker query is static
(`?speaker=a`) on split/wide.

### 3. Half-split crops pin the sprites to the outer edges

The locked Light Media Club two-shot is 1344×768. Sprite color-centers across
the aired remuxes were stable:

| Host | Slot | Mean x |
| :-- | :-- | :-- |
| Orange pebble | BOT1 / left | ~240 (takes 237–258) |
| Cobalt lozenge | BOT2 / right | ~1092 (takes 1068–1096) |

A hard half-split (`crop_right=672` / `crop_left=672`) plus
`OBS_BOUNDS_SCALE_OUTER` into the design wells put them at well-rel
**0.37 / 0.62** — scrunched on the left and right sides of the programme.

Design-preview crops (`scripts/load-design-preview.py`) now take a **400px**
window on those centers, `boundsAlignment` center (0). Left (PHASEONE) uses
`crop_top=64`. Right (deb) uses `crop_top=12` and `crop_bottom=96` so the
taller lozenge keeps her crown in frame and the extra comes off the desk.
That is a tighter zoom than the 500px window so the sprites fill more of
each well. Position alignment stays top-left so the well sits at (64, 172)
/ (1276, 172). `cropToBounds` is on so `SCALE_OUTER` cannot paint into the
logo, sponsor, or timer. Well height is 628 so the chyron at y=838 stays
clear.

| | Left well-rel | Right well-rel |
| :-- | :-- | :-- |
| 50/50 half | 0.37 | 0.62 |
| 400px on sprite | 0.50 | 0.50 |

Do not ask fal to reframe this. It is an OBS crop. Do not write the locked
spec wells in `scripts/apply-obs-layout.py` (`40/1260/620×700`) until relock;
the preview loader overrides those after `setup-obs`.

Keep overlay well CSS in `overlay-live.html` aligned with `DESIGN_WELLS`.

### 4. Overlay port and setup-obs

Live OverlayServer binds **:8765**. Design preview HTTP is **:8766**.
`WATCHDOG` must stay on

`http://127.0.0.1:8766/overlay-live.html?speaker=a`

`setup-obs` / `setup-obs-box.sh` points WATCHDOG back at :8765 and resets
wells to the locked spec. After any setup, re-run

```bash
python3 scripts/load-design-preview.py --preview-dir /tmp/runtime-design-preview --preview-port 8766
```

WASH is extra, not a contract input. It sits at z=0 and may drift
(`static=0`). H3 never sees it.

Contract furniture (`HEADLINE`, `NAME_A`, `NAME_B`, `HL_A`, `HL_B`, `CENTER`)
stays in the scenes and stays hidden. The overlay owns those plates.

### 5. Harness bookkeeping that aborted a live

- Planner `framing` over 1000 characters used to fail the whole package before
  fal. Topic-map fields already used `_fit_chars`. Framing now clips the same
  way. Cap stays 1000.
- `get_program_state` did `media_duration - media_cursor` when both were
  `None` on idle `HOST_WIDE` (`card_full` / `hold`). TypeError →
  `media_ok=False` → harness treated it as OBS disconnect and jumped to hold.
- Live work must not be `out/flights/{id}/work`. `write_evidence_bundle`
  refuses if the bundle dir already exists. Work is `out/live-work/{id}`.

### 6. Isolation and spend

- `models.py` must not contain the substring `writer`.
- `writer.py` / `discuss.py` must not contain `host_a` / `host_b` or display
  names.
- `HOST_SYSTEM` must not contain the substring `deb`.
- Live fal endpoint stays `minimax/h3-max/image-to-video`.
- Default `load_source_packet` stays locked to the Dwarkesh tweet.
  A staged lock (`binding: staged`) from `runtime_flight stage --tweet-url`
  is the other reviewed path. Live / discuss / segment accept it via
  `--source-dir`.
- Overlay CG polls `card.json`. The centre well is the official X widget
  (`platform.twitter.com/widgets.js`) via same-origin `tweet-embed.html`,
  not a transcribed POST card. The well crops the widget at 628px; it
  does not scale the whole post to fit. Solos and `card_full` can instead
  show a captured still (`tweet-shot-*.png`) cover-cropped to the wider
  plate. `?card=shot` forces the still on split too; `?card=embed` keeps
  the live widget. The transcribed card stays underneath if the widget
  does not paint. Desk chyron and ticker stay ours.
  `tweet-embed.html` loads from the overlay host (same origin) so OBS CEF
  can paint the widget. WATCHDOG on :8766 still passes
  `card_origin=http://127.0.0.1:8765` for `card.json`.
- Discuss is text-only. `--confirm-text-requests` is required. With
  `--package`, confirm == max-turns. Cap 12 turns.
- Spoken Writer lines stay at 120 chars / ~4.3s. Discuss lines stay at 220.
- Scene pack `reanchor_every` stays 5.
- Label the live inherit model `baseline` in outputs. Treat `TEXT_MODEL` as a
  secret.

## Next-flight checklist

Before `live`:

1. OBS not streaming. Record directory `out/obs-recordings`.
2. Preview HTTP on :8766 for wash. After `stage`, WATCHDOG overlay-live
   must poll the OverlayServer card (`?card_origin=http://127.0.0.1:8765`)
   or load `http://127.0.0.1:8765/overlay-live.html`.
3. Scene transition is **Cut**. `HOST_WIDE` `looping` and
   `restart_on_activate` are false.
4. Split `HOST_WIDE` crops are the 500px sprite windows, not 672/672.
5. `load-design-preview.py` has been run after the last `setup-obs`.
6. `RUNTIME_ALLOW_PAID=1`, spend cap and `--confirm-spend` match. Live CLI has
   no `--max-fal-submissions`; the clock and cap bound fal.

After the first take lands:

```bash
ffprobe -hide_banner out/live-work/<id>/ready/001.mp4
ffprobe -hide_banner out/live-work/<id>/ready/001.obs.mp4
# obs sibling must be High / yuv420p and still have AAC
```

After record stop:

```bash
ffprobe -hide_banner "out/obs-recordings/<mkv>"
ffmpeg -i "out/obs-recordings/<mkv>" -af volumedetect -f null -
# mean around -20 dB is speech. -91 dB is a silent track.
```

Wells that go to wash between takes means the director left `split` or
`HOST_WIDE` cleared. Do not "fix" that by looping the last line.

## Replay without spending

Remuxed takes from `live-20260901T155458Z` are enough to prove picture, crop,
Cut, last-frame hold, and audio:

```text
out/live-work/live-20260901T155458Z/ready/{001,003,005,006,007,008,009,010}.obs.mp4
```

Stay on `split`. `play_clip` each remux. Leave 2s after a clip ends — the
sprites should stay in the wells (last frame), not the wash. `volumedetect`
on that recording should not be −91 dB.
