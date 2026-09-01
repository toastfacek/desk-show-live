# Runtime deterministic OBS graphics spec

Target canvas: **1920×1080**. This document specifies the deterministic layer only; generated hosts/set remain one 1344×768 wide source described by `studio.yaml`.

**Relocked 2026-09-01.** The accepted rationale and old/new comparison are preserved in [deliverables/RELOCK_PROPOSAL.md](deliverables/RELOCK_PROPOSAL.md). This document is the resulting pixel grammar.

## Status of measurements

- **Project-locked** values are Runtime decisions: floating 64 px furniture, sharp borderless panels, maximum 8 px radius, no glow, no skew, and 3–4 px minimum essential rules at 1080p.
- **Provisional** values are implementation starting points not established as universal broadcast or Twitch standards. They must pass the validation ladder at the end before M0 lock.
- Evidence and rationale are consolidated in the [style report](runtime-style-report.md) and source lanes [L3](findings/L3-broadcast-graphics.md), [L4](findings/L4-multibox-layouts.md), [L5](findings/L5-type-color.md) and [L6](findings/L6-motion-idents.md).

## Inventory

Required components:

1. `SHOW_BUG`
2. `LIVE_BADGE`
3. `CLOCK`
4. `SPONSOR_CELL`
5. `HOST_FRAME_L`, `HOST_FRAME_R`
6. `HOST_ID_L`, `HOST_ID_R`
7. `SPEAKER_STATE_L`, `SPEAKER_STATE_R`
8. `CENTER_CARD` with payload templates
9. `CHYRON` with kicker and headline
10. `TICKER` with paginated and crawl modes
11. `STINGER_UTILITY_080`, `STINGER_UTILITY_120`
12. `BUMPER_03`, `BUMPER_05`, `OPEN_10`

Optional components are a static secondary sponsor strip and a chat panel. Neither may displace or shrink required components for M0.

## Layering

Back to front:

| Z | Layer | Rule |
| ---: | --- | --- |
| 0 | `PROGRAM_BG` | Solid `foundation` fallback; never transparent |
| 10 | `HOST_WIDE` | Dedicated full-source item for `wide` only |
| 20 | `HOST_CROP_L/R` | Two synchronized instances of the same media source |
| 30 | host dim plates | Off by default; max provisional 16% neutral black for text-heavy centre cards |
| 40 | active host-name plate | Attached to apertures; exactly one inverted when speaker is known |
| 50 | `CENTER_CARD` shell and payload | Covers source join whenever present |
| 60 | host IDs | Attached to host apertures |
| 70 | chyron, ticker, sponsor furniture | Opaque bottom stack |
| 80 | unified system rail | Mark, LIVE, segment, clock and sponsor; persistent |
| 90 | stinger overlay + track matte | Must fully occlude the cut once |
| 100 | panic/hold card | Highest operational layer |

The source join must never depend on a visible one-pixel seam. The two crops overlap beneath the centre card or an opaque divider. No alpha gap may expose `PROGRAM_BG`.

## Tokens

### Geometry

| Token | Value | Status |
| --- | ---: | --- |
| `space-1/2/4` | 4 / 8 / 16 px | Provisional spacing rhythm |
| `rule-essential` | 4 px | Project-locked within required 3–4 px range |
| `divider-source` | 8 px opaque | Project-locked |
| `radius-sm` | 4 px | Provisional |
| `radius-max` | 8 px | Project-locked maximum |
| `skew` | 0° | Project-locked |
| `glow` | none | Project-locked |
| `shadow` | none for essential separation | Project-locked |

All geometry lands on whole canvas pixels after browser/OBS scaling. Avoid fractional transforms.

### Colour

| Token | Value | Use |
| --- | --- | --- |
| `foundation` | `#0B0A08` | Canvas, primary furniture |
| `plate` | `#15130F` at 93% | Raised cards; essential text still meets ≥7:1 |
| `text-primary` | `#F4F1EA` | Essential text |
| `text-secondary` | `#ADA69A` | Metadata |
| `lemon` | `#D4E04A` | Programme accent; desk rule and kicker chip only |
| `live` | `#E2543F` | 10 px LIVE dot only |
| `gain` | `#A3BE9C` | Positive state with sign/shape |
| `loss` | `#D89A88` | Negative state with sign/shape |

Furniture remains warm-dark/off-white. Lemon is the only saturated furniture colour and never identifies a host. No gradients, transparency-based glass, RGB masks or fine textures.

### Type

Bundle pinned static font files and their OFL texts with the OBS project.

| Role | Family/style | Provisional size |
| --- | --- | ---: |
| short kicker | Archivo 700, uppercase | 28 px |
| headline | Archivo 700, sentence case | 42 px |
| host name | Archivo 700, prescribed case | 40 px |
| handle/metadata | Inter 600 | 28 px |
| ticker/body | Inter 600 | 28 px |
| clock/LIVE/system | JetBrains Mono 500, tabular numerals for clock | 30 px |

Archivo, Inter and JetBrains Mono use the SIL Open Font License 1.1 and are suitable for commercial video titling; retain licence/copyright files when distributing fonts ([Archivo OFL](https://github.com/google/fonts/blob/main/ofl/archivo/OFL.txt), [Inter OFL](https://github.com/rsms/inter/blob/v4.0/LICENSE.txt), [JetBrains Mono OFL](https://github.com/JetBrains/JetBrainsMono/blob/master/OFL.txt), [SIL OFL FAQ](https://software.sil.org/downloads/r/oflt/OFL-FAQ.txt)).

Use Archivo's width axis (`wdth` 62–125) to fit display copy before reducing size. JetBrains Mono never takes a headline, card body or host name.

Essential text must not fall below the provisional 26 px floor. Use fixed-width regions, copy editing, wrapping and ellipsis before reducing size. Verify `font-variant-numeric: tabular-nums` in the actual OBS browser source; if unsupported, pin a static Inter build known to expose tabular figures. All essential text sits on a composited token plate and targets at least 7:1 calculated contrast as a Runtime margin, not a sourced broadcast threshold.

## Safe area and furniture

The following are **provisional Runtime safe regions**, not Twitch standards:

- critical horizontal inset: 64 px
- critical top inset: 48 px
- critical bottom inset: 54 px
- maximum bottom furniture reservation: 190 px
- working host/card top: 140 px
- working host/card bottom: 800 px

Nonessential solid colour may bleed to canvas edges. Do not place a unique fact only in the lowest 54 px because player controls may cover it.

Provisional bottom stack:

| Element | Rectangle |
| --- | --- |
| chyron | `x=64, y=838, w=1792, h=118` |
| ticker | `x=64, y=972, w=1792, h=56` |

The ticker remains the only moving row.

Top furniture uses one system rail at `x=64, y=48, w=1792, h=60`. The accepted two-mass mark, LIVE, segment counter and clock form the left lockup; sponsor content is right-aligned at the same 64 px canvas inset.

## Layouts

### Fixed source transforms

`HOST_CROP_L` and `HOST_CROP_R` reference the same `HOST_WIDE` media source and playhead. Each selects exactly one 50% source half. Within the multibox family, its source crop and scale are fixed; only the 580×660 aperture position changes. Never zoom or rescale a host to indicate speech.

The exact cover transform is **provisional and resolution-profile-specific**:

- 768p input half: start from 672×768; cover a 580×660 aperture at scale 0.863 and trim only the minimum horizontal excess.
- 480p input half: start from 427×480; cover the same aperture and trim only the minimum horizontal excess.

Store and test separate 768p and 480p transform profiles. Do not let OBS choose an implicit stretch.

### `split` / host–content–host

Provisional rectangles:

- left host aperture: `x=64, y=140, w=580, h=660`
- centre card: `x=668, y=140, w=584, h=660`
- right host aperture: `x=1276, y=140, w=580, h=660`

The centre shell sits above both host items and fully covers their inner edges. The 24 px gutters remain opaque beneath it.

### `paired`

For a centre-free discussion, translate the fixed apertures to:

- left: `x=380, y=140, w=580, h=660`
- right: `x=960, y=140, w=580, h=660`

Overlap source picture by at least 4 provisional pixels beneath a project-locked opaque 8 px divider centred at `x=956..964`. Crop origins remain aligned so desk height, eyeline and background continuity are truthful. Never expose a one-pixel source seam.

### `wide`

Use a separate `HOST_WIDE` scene item fit to the 1920×1080 programme canvas behind furniture. Do not derive `wide` by changing either fixed crop item. This view is expected to be the most demanding 480p test.

### `solo_l` / `solo_r`

For M0, retain the selected host's fixed 580×660 transform and move its aperture into the appropriate composition; use the remaining field for a centre payload or neutral furniture. Do not enlarge the crop. Any future enlarged solo is a separate approved source profile and requires its own 480p encode test.

### `card_full` and `hold`

`card_full` uses the centre-card grammar expanded inside `x=64, y=140, w=1792, h=660`, stopping above the bottom stack. Host audio remains independent.

`hold` uses the same geometry with a baked non-text background and OBS-rendered status copy. Ticker and top furniture may continue; no frozen host frame should be visible.

## Centre-card payload rules

The 584×660 shell has a safe interior of `x=24, y=40, w=536, h=580` relative to the shell. One payload template changes inside this shell; outer geometry never changes.

Common rules:

- 93% `plate` background with no border; essential type remains ≥7:1 on the composited panel.
- Maximum two hierarchy levels beyond the payload itself.
- No text baked into generated imagery; all labels are HTML/OBS.
- No microtype, hairline charts, fine grid, fine dither or low-contrast gradient.
- Overflow order: edit copy → wrap within limits → ellipsize; never shrink below 26 px.

Payloads:

- **Post:** source label + author line + body. Body maximum provisional 240 characters and 8 lines; strip unsafe formatting and external images by default.
- **Chart:** title + one plot + up to three labelled series. Axes/rules are at least 4 px; direct labels replace a dense legend. Values use Inter tabular figures and signs/shapes.
- **Static image:** `contain`, never distort; use a neutral matte. Any essential caption is OBS-rendered outside the image.
- **Guest video:** `cover` the safe interior with an approved focal crop; attach name/state furniture using the host grammar.
- **Fallback/error:** solid plate, short OBS status, no broken-image icon or raw URL.

For text-heavy post/chart cards, a provisional 16% black dim plate may cover the host pictures while leaving borders and IDs undimmed. Guest payloads do not dim hosts.

## Speaker state

Speaker state is deterministic and never audio-driven:

- inactive host-name plate: normal `plate` with `text-primary`
- active host-name plate: ink on bone inversion at 17.5:1
- active plate carries the same small cursor used by the on-air wordmark
- exactly one plate is inverted when a speaker is known; neither is inverted when unknown
- no colour-only state, extra tab, border, glow, pulse loop, zoom or source-opacity flutter

Provisional response starting points: 300 ms attack and 600 ms release. The director supplies the intended speaker, so coughs and generated mouth errors cannot flash the state. At a handoff, allow no more than one active state; when unknown, show neither.

Host IDs preserve exact case: `PHASEONE[lol]` and `deb`. Provisional dwell is 5–7 seconds on first appearance and 2–3 seconds on re-identification; the source lane does not establish these as standards.

## Chyron and ticker

The 118 px chyron contains:

- a fixed-width kicker chip
- a flexible headline region
- maximum one 28 px kicker line and two 42 px headline lines
- stationary plate during ordinary topic changes; replace copy under a short vertical clip

Ticker rules:

- one moving information row maximum
- preferred mode: paginated items held a provisional 6–8 seconds
- crawl fallback: begin near a provisional 210 words/minute equivalent and tune by encode
- each item contains one symbol/name, one value and one change, or one short news sentence
- items separate with a 4 px solid rule or at least 20 px clear gap
- market changes show `▲ +value` or `▼ −value` plus colour
- no continuously moving sponsor row beneath a moving ticker
- no unique critical fact exists only in the ticker
- update text between whole frames; do not reveal partial data writes

## Sponsor furniture

Sponsor content is a static cell right-aligned inside the 60 px system rail. Use `PRESENTED BY` in JetBrains Mono 500 at no less than 26 px plus an approved high-contrast sponsor mark.

Rules:

- sponsor cell is opaque and visually subordinate to LIVE/clock
- one sponsor at a time
- provisional minimum hold: 8–12 seconds
- sponsor changes occur only while ticker motion is paused or between paginated ticker items
- no simultaneous logo animation and ticker crawl
- no second sponsor row is permitted beneath the ticker

## Code layer

- No ASCII textural cell is below 20 px at 1080; no mosaic or Bayer cell is below 8 px.
- A ground wash may occupy only margins and gutters beneath opaque pictures/panels. It never sits behind essential type.
- Host-free fields may use coarse ASCII/mosaic texture.
- Texture is static whenever a host is visible. Drift in host-free states stays behind a flag until a received Twitch rendition passes the validation ladder.

## Motion and audio test starts

All values in this section are **provisional test starting points** unless stated otherwise.

| Asset/state | Duration | Starting behaviour |
| --- | ---: | --- |
| utility wipe | 0.80 s / 24 frames at 30 fps | cover cut by frame 12; clear by frame 24 |
| dramatic utility wipe | 1.20 s / 36 frames | same geometry, more hold |
| text/plate reveal | 0.27–0.40 s / 8–12 frames | opaque clip, ≤2-frame accent stagger |
| text/plate exit | 0.20–0.33 s / 6–10 frames | reverse clip |
| signal fault | 0.067–0.133 s / 2–4 frames | sparse horizontal tear/block only |
| subject sting | 3.0 s | resolved sonic button |
| segment bumper | 5.0 s | stable title hold in final 0.75–1.0 s |
| cold open | 10.0 s | acquire → lock → title hold |

Track-matte stingers must use one combined overlay/matte master to avoid decode drift, following [OBS guidance](https://obsproject.com/kb/track-matte-stinger-transitions). Every utility wipe fully covers the old and new scenes at the cut. Exact matte crossing and cut frames are locked only after encode testing.

Audio motif: dry relay click, rising two-note pulse, warm low-frequency button. Deliver full mix, percussion/noise, tonal motif, button and bed stems, plus exact-duration edits. For bed ducking, begin with the official OBS sidechain recommendations of 100 ms attack and 600 ms release, then tune threshold, ratio and gain reduction with programme audio ([OBS compressor](https://obsproject.com/kb/compressor-filter)). No loudness target is specified until measured.

## 1080 → Twitch → 480p validation checklist

Test a representative 60–90 second programme containing both generation profiles, every required graphic, a fast data change and both utility wipes.

1. Capture a lossless/native 1920×1080 OBS master.
2. Encode/stream with the intended Twitch bitrate, frame rate, colour range and audio chain; record the received output rather than relying on OBS preview.
3. Inspect the received 1080 rendition at 100% and a Twitch 480p rendition at 100%; include a normal viewing-distance/mobile check.
4. Verify all 4 px rules remain continuous and borderless panel edges remain clean without ringing.
5. Verify the card/divider hides the source join in motion, during layout movement and on the exact transition frame.
6. Verify fixed host crops do not zoom, stretch or jump between `paired`, `split` and solo compositions.
7. Run both 768p and 480p host inputs through `split` and `wide`; judge identity, eyes, contour stability and shell/rim separation independently.
8. Confirm every essential 26–28 px sample remains readable; test `PHASEONE[lol]`, lowercase `deb`, narrow counters, brackets, percentages and a worst-case two-line headline.
9. Confirm Inter numerals are tabular and do not shift columns as clock/market values update.
10. Confirm the active name-plate inversion remains unmistakable in grayscale and common colour-vision simulations without colour information.
11. Confirm gain/loss signs and ▲/▼ remain visible when chroma is softened.
12. Confirm post overflow, long names and missing payloads fail safely without shrinking type or exposing raw URLs.
13. Confirm only one row moves; measure crawl/pagination comprehension at 480p and revise cadence.
14. Inspect wipes frame by frame for incomplete cover, matte fringing, banding and a visible host-chain discontinuity.
15. Listen for pumping, clipped stings and speech masking; tune ducking beyond the 100/600 ms starting values.
16. Check player controls against bug, ticker and sponsor placement; remove any unique fact from covered regions.
17. Confirm no host-visible texture moves; test any flagged host-free drift for bitrate cost and crawling artifacts.
18. Lock remaining provisional timing values only after the test capture, recording the accepted OBS profile, bitrate, frame rate and rendition.
