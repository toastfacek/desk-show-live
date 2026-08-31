# Production view assets — what to make (and what not to)

Runtime already chose the TBPN architecture: **hosts are one layer; titles, tickers, sponsor bars, and the card are another computer.** The generated picture stays one 1344×768 two-shot. A TBPN-par *view* is 100% the deterministic 1080 layer plus a small family of baked motion and sound. It is not more fal pixels, not an ATEM, and not a cloned forest-green F1 suite.

Named shows stay in this file. They never enter a generation prompt, a Writer system prompt, or on-air copy.

The locked pixel grammar is [runtime-graphics-spec.md](../runtime-graphics-spec.md). Type and colour evidence is [L5](L5-type-color.md). Motion family is [L6](L6-motion-idents.md). Layout wells are [L4](L4-multibox-layouts.md). This note is the **asset bill**: what files and templates must exist before that spec can appear on programme.

A static 1920×1080 target frame lives at [../mocks/production-view.html](../mocks/production-view.html).

## What “on par” means here

TBPN’s picture is SportsCenter furniture on a cinema-camera desk: one object on screen, two hosts commenting on it, a clock that kills the topic, a chyron that could survive as a clip. Their control room is a vMix-plus-Blackmagic rack. **Do not buy that rack.** Copy the split:

| Their computer | Runtime equivalent | Job |
| --- | --- | --- |
| FX3s into an ATEM | `HOST_WIDE` (H3 clip or hero still) | Faces and desk only. No readable type. |
| vMix HTML5 CG | One browser overlay at 1920×1080 | Bug, LIVE, clock, names, speaker tabs, card, chyron, ticker, hold. |
| Area Technology chyron suite | Overlay templates + JSON payloads | Data-driven copy. Type is never pixels in the camera. |
| HyperDeck ISOs / clip factory | Later. Not M0. | Afternoon clips. |
| Teradek + Restream | Later encoder / fan-out. | Distribution, not the view. |

If the overlay is a hold card and the OBS text sources are empty, the show looks like a webcam two-shot. That is the whole gap.

## What exists today

| Layer | On disk | On programme |
| --- | --- | --- |
| Hosts / hero | Pack Manager (`pack-manager/data/`, gitignored). Seed `pack-manager/fixtures/hero_wide.png`. | `HOST_WIDE` media source, split-cropped. |
| Live overlay | `runtime-flight/overlay/{index.html,app.js,style.css}` | Tweet card + opaque **STAND BY** hold. Default `body.hold`. IBM Plex / gold, not the L5 tokens. |
| OBS contract | `HOST_WIDE`, `CENTER`, `HEADLINE`, `NAME_A/B`, `HL_A/B`, `BED`, `WATCHDOG` | Empty `text_ft2` / empty `image_source` / empty `BED`. Highlight bars exist as 8 px plates. `WATCHDOG` is a full-frame browser; hold covers the desk. |
| Fonts | Specified (Barlow Condensed + Inter, OFL). | Not bundled. Overlay falls back to system Plex. |
| Show bug, LIVE, clock, sponsor | Specified. | Missing. |
| Host frames / IDs / speaker tabs | Specified. | Missing (names are empty text sources). |
| Centre-card templates | Specified (post / chart / image / guest / error). | One tweet card, wrong size and palette, only when hold is off. |
| Chyron + ticker | Specified. | Missing. |
| Stingers / bumpers / open | Specified in L6. | Missing. No files under `assets/`. |
| Audio bed / sting stems | Specified. | Missing. |
| Writer land-line → chyron | Segment research (elsewhere). | Writer does not know open/close/land rules. |

The harness already treats bumpers and `card_full` as free minutes. There is nothing to play.

## Asset bill

Make these. Do not generate them inside H3.

### 0. Identity kit (one afternoon, unblocks everything)

These are files, not prompts.

| Asset | Spec | Notes |
| --- | --- | --- |
| `fonts/BarlowCondensed-Bold.ttf` (+ OFL.txt) | L5 / graphics spec | Headlines, names, kicker. Weight 700. |
| `fonts/Inter-SemiBold.ttf`, `Inter-Bold.ttf` (+ OFL.txt) | L5 | Ticker, clock, LIVE, metadata. Pin a static build that exposes `tnum`. |
| `tokens.css` | graphics spec colour + type tables | Single source for overlay and mocks. No second palette. |
| `SHOW_BUG.svg` / 72×72 PNG | `x=96,y=54,w=72,h=72` | Original mark. Not a letterform that H3 would have to draw. High-contrast on `#101116`. |
| Wordmark lockup | Optional; bug can stand alone | “DESK SHOW” in Barlow if needed. Do not use Record Laser or TBPN green. |

**Do not make:** a forest-green F1 clone, a Sharp Type license, sponsor density as wallpaper, or any mark that has to be regenerated per take.

### 1. Live CG — one HTML overlay (the real production view)

Replace the current overlay *and* stop using OBS `text_ft2` for furniture. TBPN’s chyron is a templated web CG talking to data. Same job: one browser source, transparent body, opaque plates.

Required templates, all 1920×1080, all driven by JSON:

| Template | Geometry (provisional) | Copy rules |
| --- | --- | --- |
| `SHOW_BUG` | 72×72 at 96,54 | Persistent. Never animates on topic change. |
| `LIVE_BADGE` | 112×40 at 1584,54 | Inter 700, 30 px. Persistent while programme is live. |
| `CLOCK` | 120×40 at 1704,54 | Inter 700 tabular. Show clock, not a countdown that empties the well on air. |
| `SPONSOR_CELL` | 220×40 at 96,134 | `PRESENTED BY` + one mark. Static 8–12 s. No second moving row. |
| `HOST_FRAME_L/R` | 8 px on 620×700 apertures | `plate` idle; `amber` BOT1 / `teal` BOT2 when that host is intended speaker. |
| `SPEAKER_STATE_L/R` | Tab on top-left of frame | Solid `ON AIR` lozenge. Colour alone is illegal. |
| `HOST_ID_L/R` | Attached to aperture | Exact case: `PHASEONE[lol]`, `deb`. 5–7 s first appearance. |
| `CENTER_CARD` | 660,100,600×700 | One payload at a time. See §2. |
| `CHYRON` | 0,900,1920×96 | Kicker 240 px + two-line headline. **This is the land line**, not the tweet’s first clause. |
| `TICKER` | 0,996,1920×52 | One row. Paginated 6–8 s preferred. Symbol / value / `▲ +n` or one short sentence. |
| `HOLD` | z=100, full frame | Baked plate + OBS status. Default **off**. Today it is on, which is why the desk disappears. |

**Kill or demote** as furniture: `HEADLINE`, `NAME_A`, `NAME_B` as separate OBS text inputs. They will drift. Keep `HOST_WIDE` crops, `CENTER` only if a guest/image must be a media source keyed *into* the card well, `BED` for audio, `WATCHDOG` only if hold stays a separate panic layer.

Minimum overlay JSON (one object, one poll):

```json
{
  "layout": "split",
  "live": true,
  "clock": "16:45:02",
  "speaker": "BOT1",
  "hosts": {
    "BOT1": { "name": "PHASEONE[lol]", "id_visible": true },
    "BOT2": { "name": "deb", "id_visible": true }
  },
  "card": { "template": "post", "kicker": "POST", "author": "@handle", "body": "…" },
  "chyron": { "kicker": "DESK", "headline": "The land line that could be the clip." },
  "ticker": [{ "symbol": "ACME", "value": "12.4", "change": "+0.8", "sign": "up" }],
  "sponsor": { "label": "PRESENTED BY", "name": "—" },
  "hold": false
}
```

`let_card` is a Director move: no host line, card stays up, ticker may page. The overlay already has the object; it does not need a new graphic.

### 2. Centre-card payloads (five templates, one shell)

The 600×700 shell never changes. Only the interior (552×620) swaps.

| Template | Must include | Must not include |
| --- | --- | --- |
| **post** | Source label, author, body ≤240 chars / 8 lines | Embedded tweet chrome, avatars pulled live, raw URLs |
| **chart** | Title, one plot, ≤3 labelled series, 4 px rules, Inter tabular + `▲/▼` | Hairline grids, legends that require 12 px type |
| **image** | `contain` on a `plate` matte; caption outside the image | Distorted `cover` of a screenshot that already has type |
| **guest** | Cover crop + name/state using host grammar | Dim plates on the hosts |
| **error** | Short status on a solid plate | Broken-image icon, exception text, URLs |

Post is M0. Chart and image are the next free minutes (TBPN’s “let the clip speak”). Guest is v2. All labels are HTML. If a screenshot of a tweet is the evidence, strip or recrop so the overlay still owns the readable words.

### 3. Baked motion (the period after a land)

TBPN (and PTI) sting so 90 seconds does not feel like a podcast someone forgot to stop. Bake once at true 1080. **No readable type in the generated plate.** Overlay or OBS sets the title on the hold frames.

| File | Duration | Job |
| --- | --- | --- |
| `assets/stingers/utility_080.webm` | 0.80 s / 24 frames @30 | Routine cut. Combined overlay+matte master. Cover by frame 12. |
| `assets/stingers/utility_120.webm` | 1.20 s | Same geometry, more hold. Layout changes and re-anchors. |
| `assets/bumpers/sting_03.webm` | 3.0 s | Subject change. Final 0.45–0.60 s stable for a title. |
| `assets/bumpers/segment_05.webm` | 5.0 s | Segment boundary. Title hold in last 0.75–1.0 s. |
| `assets/bumpers/open_10.webm` | 10.0 s | Show start or major return only. |
| Fault library (6 stills or 2–4 frame bursts) | — | Authored tears for drift, not a permanent glitch look. |

Prompt-safe plates only (L6 wording). One motion/sound cadence for the whole family: sync sweep, geometric lock, ready button. Do not replay `open_10` between topics.

### 4. Audio identity

| Stem | Length | Job |
| --- | --- | --- |
| `assets/audio/bed_loop.wav` | 30–60 s seamless | Sparse, continuous. Duck under speech (OBS sidechain 100 ms / 600 ms start). |
| `wipe_080`, `wipe_120` | match picture | Noise impulse + short tonal button. |
| `sting_03` | 3.0 s | Resolved. Plays under the land. |
| `bumper_05_in` / `_out` | 5.0 s | In unresolved (falls into bed). Out resolved. |
| `open_10` | 10.0 s | Cold open only. |
| Prints | — | Full mix, percussion/noise, tonal motif, button, bed. Never time-stretch live. |

No loudness target until a real encode. No catchphrases the video model has to pronounce.

### 5. Still plates (already in the architecture, still missing as files)

| Asset | Job |
| --- | --- |
| Locked hero / pack baseline | Clip 0 and re-anchor. Exists in Pack Manager, not as a furniture asset. |
| `hold` background | Non-text baked plate under OBS status. Today hold is a CSS fill. |
| `card_full` expansion | Same card grammar, safe rect `96,54,1728×846`. Needs the overlay, not a new generator. |
| Ad-read stills (later) | Free minutes. One sponsor cell at a time. |

### 6. Do not create

- ATEM / vMix / Teradek / Restream / Hollyland. The view does not care.
- Ross / Chyron / iNews. There is no NRCS. The rundown is already a package object.
- A second generated wide that includes chyrons. Type in H3 will mutate.
- Crossfire lower-thirds, “debate” bugs, or catchphrase bugs.
- Chat-as-third-host chrome (v2). Displaying chat is cheap; letting it steer is not M0.
- Scoreboards, J-screens, side rails, glass, glow, skew, gradients.
- DIN 2014, Record Laser, or any type that needs a seat.

## Build order

The cheapest path to a picture that reads as a show:

1. **Bundle fonts + `tokens.css` + original bug.** One commit. Unblocks every template.
2. **Rewrite the overlay as a transparent CG** with hold **off** by default. Persistent: bug, LIVE, clock. Attached: frames, IDs, speaker tabs. Bottom: chyron + ticker. Centre: post card. This is the TBPN “other computer.”
3. **Wire overlay JSON** from the Director (speaker, chyron from the land, ticker from the rundown, card from the package). Stop writing names into OBS text sources.
4. **Bake `utility_080` + `sting_03` + bed loop.** A land without a sting still feels like a podcast.
5. **`segment_05` + `open_10` + remaining stems.** Free minutes. Cheap-spend policy can actually go somewhere.
6. Chart / image card templates. Guest last.

Do not start with bumpers if the live desk still has no chyron. Furniture is what makes a still frame look like television; bumpers are what makes the hour survivable.

## How this serves the segment, not just the picture

The first TBPN writeup locked the *talk*: complementary questions, do not read the card, one idea per take, land while an angle is still unsaid. The production view has to enforce that:

- The **card** is the shared object. Hosts do not recap it. Overlay may `let_card` with no line.
- The **chyron** is the land, written as one clip-safe sentence. If the Writer opens by reading the card, the chyron will duplicate it and the frame will look like a zoomed tweet.
- The **ticker** is a third channel (PTI rundown / SportsCenter scores). It must not repeat the chyron.
- A **sting** is the period. Without it, 90 seconds has no lifecycle.
- **Speaker tabs** come from the Director, not audio. That is how BOT1/BOT2 stay complementary on a 5-second take instead of both looking “on.”

Assign Segmenter angles to one host axis in copy; the overlay only needs to know who is `ON AIR`.

## Validation

Do not lock pixels until the [1080 → Twitch → 480p checklist](../runtime-graphics-spec.md) has a real encode of: split + post card + chyron + ticker + both utility wipes + a clock tick + a speaker handoff. The mock is a target, not a lock.

## What this pass did not do

- Did not watch a TBPN episode end-to-end. Stack claims in the prior chat stay vendor/interview-sourced.
- Did not implement the live overlay rewrite or bake motion/audio.
- Did not add named-show language to any Writer or H3 prompt.
