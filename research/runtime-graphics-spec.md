# Runtime deterministic OBS graphics spec

Target canvas: **1920×1080**. This document specifies the deterministic layer only; generated hosts/set remain one 1344×768 wide source described by `studio.yaml`.

## Status of measurements

- **Project-locked** values are Runtime decisions: 8 px opaque host/card borders, maximum 8 px radius, no glow, no skew, and 3–4 px minimum essential rules at 1080p.
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
| 40 | host borders and speaker tabs | Opaque; attached to apertures |
| 50 | `CENTER_CARD` shell and payload | Covers source join whenever present |
| 60 | host IDs | Attached to host apertures |
| 70 | chyron, ticker, sponsor furniture | Opaque bottom stack |
| 80 | show bug, LIVE, clock, top sponsor cell | Persistent |
| 90 | stinger overlay + track matte | Must fully occlude the cut once |
| 100 | panic/hold card | Highest operational layer |

The source join must never depend on a visible one-pixel seam. The two crops overlap beneath the centre card or an opaque divider. No alpha gap may expose `PROGRAM_BG`.

## Tokens

### Geometry

| Token | Value | Status |
| --- | ---: | --- |
| `space-1/2/4` | 4 / 8 / 16 px | Provisional spacing rhythm |
| `rule-essential` | 4 px | Project-locked within required 3–4 px range |
| `border-frame` | 8 px | Project-locked |
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
| `foundation` | `#101116` | Canvas, primary furniture |
| `plate` | `#171A20` | Raised cards, tabs |
| `text-primary` | `#F2F0E8` | Essential text |
| `text-secondary` | `#A9ADB7` | Metadata |
| `amber` | `#F2A541` | BOT1/accent state |
| `teal` | `#2FB7B2` | BOT2/accent state |
| `gain` | `#4FC58B` | Positive state with sign/shape |
| `loss` | `#E05D68` | Negative state with sign/shape |

Furniture remains charcoal/off-white. Amber and teal occupy small tabs, 4–8 px rules or short labels, not entire shells. No gradients, transparency-based glass, RGB masks or fine textures.

### Type

Bundle pinned static font files and their OFL texts with the OBS project.

| Role | Family/style | Provisional size |
| --- | --- | ---: |
| short kicker | Barlow Condensed 700, uppercase | 28 px |
| headline | Barlow Condensed 700, sentence case | 42 px |
| host name | Barlow Condensed 700, prescribed case | 40 px |
| handle/metadata | Inter 600 | 28 px |
| ticker/body | Inter 600 | 28 px |
| clock/LIVE | Inter 700, tabular numerals for clock | 30 px |

Barlow Condensed and Inter use the SIL Open Font License 1.1 and are suitable for commercial video titling; retain licence/copyright files when distributing fonts ([Barlow OFL](https://github.com/google/fonts/blob/main/ofl/barlowcondensed/OFL.txt), [Inter OFL](https://github.com/rsms/inter/blob/v4.0/LICENSE.txt), [SIL OFL FAQ](https://software.sil.org/downloads/r/oflt/OFL-FAQ.txt)).

Essential text must not fall below the provisional 26 px floor. Use fixed-width regions, copy editing, wrapping and ellipsis before reducing size. Verify `font-variant-numeric: tabular-nums` in the actual OBS browser source; if unsupported, pin a static Inter build known to expose tabular figures. All essential text sits on an opaque token plate and targets at least 7:1 calculated contrast as a Runtime margin, not a sourced broadcast threshold.

## Safe area and furniture

The following are **provisional Runtime safe regions**, not Twitch standards:

- critical horizontal inset: 96 px
- critical top inset: 54 px
- critical bottom inset: 54 px
- maximum bottom furniture reservation: 180 px
- working host/card top: 100 px
- working host/card bottom: 800 px

Nonessential solid colour may bleed to canvas edges. Do not place a unique fact only in the lowest 54 px because player controls may cover it.

Provisional bottom stack:

| Element | Rectangle |
| --- | --- |
| chyron | `x=0, y=900, w=1920, h=96` |
| ticker | `x=0, y=996, w=1920, h=52` |
| optional sponsor strip | `x=0, y=1048, w=1920, h=32` |

The optional sponsor strip is nonessential and may be omitted. Prefer the top sponsor cell so the ticker remains the only moving row.

Top furniture starting rectangles are provisional:

- bug: `x=96, y=54, w=72, h=72`
- LIVE: `x=1584, y=54, w=112, h=40`
- clock: `x=1704, y=54, w=120, h=40`
- sponsor cell: `x=96, y=134, w=220, h=40`

## Layouts

### Fixed source transforms

`HOST_CROP_L` and `HOST_CROP_R` reference the same `HOST_WIDE` media source and playhead. Each selects exactly one 50% source half. Within the multibox family, its source crop and scale are fixed; only the 620×700 aperture position changes. Never zoom or rescale a host to indicate speech.

The exact cover transform is **provisional and resolution-profile-specific**:

- 768p input half: start from 672×768; cover a 620×700 aperture and trim only the minimum vertical excess.
- 480p input half: start from 427×480; cover the same aperture and trim only the minimum horizontal excess.

Store and test separate 768p and 480p transform profiles. Do not let OBS choose an implicit stretch.

### `split` / host–content–host

Provisional rectangles:

- left host aperture: `x=40, y=100, w=620, h=700`
- centre card: `x=660, y=100, w=600, h=700`
- right host aperture: `x=1260, y=100, w=620, h=700`

The centre shell sits above both host items and fully covers their inner edges. Its 8 px border is included inside the 600×700 rectangle.

### `paired`

For a centre-free discussion, translate the fixed apertures to:

- left: `x=340, y=100, w=620, h=700`
- right: `x=960, y=100, w=620, h=700`

Overlap source picture by at least 4 provisional pixels beneath a project-locked opaque 8 px divider centred at `x=956..964`. Crop origins remain aligned so desk height, eyeline and background continuity are truthful. Never expose a one-pixel source seam.

### `wide`

Use a separate `HOST_WIDE` scene item fit to the 1920×1080 programme canvas behind furniture. Do not derive `wide` by changing either fixed crop item. This view is expected to be the most demanding 480p test.

### `solo_l` / `solo_r`

For M0, retain the selected host's fixed 620×700 transform and move its aperture into the appropriate composition; use the remaining field for a centre payload or neutral furniture. Do not enlarge the crop. Any future enlarged solo is a separate approved source profile and requires its own 480p encode test.

### `card_full` and `hold`

`card_full` uses the opaque centre-card grammar expanded inside the provisional safe rectangle `x=96, y=54, w=1728, h=846`, stopping above the bottom stack. Host audio remains independent.

`hold` uses the same geometry with a baked non-text background and OBS-rendered status copy. Ticker and top furniture may continue; no frozen host frame should be visible.

## Centre-card payload rules

The 600×700 shell has a provisional safe interior of `x=24, y=40, w=552, h=620` relative to the shell. One payload template changes inside this shell; outer geometry never changes.

Common rules:

- Opaque `plate` background and 8 px border.
- Maximum two hierarchy levels beyond the payload itself.
- No text baked into generated imagery; all labels are HTML/OBS.
- No microtype, hairline charts, fine grid, dither or low-contrast gradient.
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

- inactive frame: 8 px `plate`
- BOT1 active frame: 8 px `amber`
- BOT2 active frame: 8 px `teal`
- active state also displays a solid `ON AIR` tab or filled lozenge attached to the top-left of that host frame
- the tab/shape is mandatory redundancy; colour alone is insufficient
- no glow, pulse loop, zoom or source-opacity flutter

Provisional response starting points: 300 ms attack and 600 ms release. The director supplies the intended speaker, so coughs and generated mouth errors cannot flash the state. At a handoff, allow no more than one active state; when unknown, show neither.

Host IDs preserve exact case: `PHASEONE[lol]` and `deb`. Provisional dwell is 5–7 seconds on first appearance and 2–3 seconds on re-identification; the source lane does not establish these as standards.

## Chyron and ticker

The 96 px provisional chyron contains:

- a fixed-width kicker cell, provisional 240 px
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

Preferred sponsor placement is a static 220×40 provisional top cell attached to the bug or clock group. Use `PRESENTED BY` in Inter 600 plus an approved high-contrast sponsor mark.

Rules:

- sponsor cell is opaque and visually subordinate to LIVE/clock
- one sponsor at a time
- provisional minimum hold: 8–12 seconds
- sponsor changes occur only while ticker motion is paused or between paginated ticker items
- no simultaneous logo animation and ticker crawl
- if a 32 px bottom sponsor strip is used, it replaces other nonessential content and carries no unique information

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
4. Verify all 4 px rules remain continuous and every 8 px border remains opaque without ringing.
5. Verify the card/divider hides the source join in motion, during layout movement and on the exact transition frame.
6. Verify fixed host crops do not zoom, stretch or jump between `paired`, `split` and solo compositions.
7. Run both 768p and 480p host inputs through `split` and `wide`; judge identity, eyes, contour stability and shell/rim separation independently.
8. Confirm every essential 26–28 px sample remains readable; test `PHASEONE[lol]`, lowercase `deb`, narrow counters, brackets, percentages and a worst-case two-line headline.
9. Confirm Inter numerals are tabular and do not shift columns as clock/market values update.
10. Confirm amber/teal active states remain distinguishable in grayscale and common colour-vision simulations because the solid state tab also changes.
11. Confirm gain/loss signs and ▲/▼ remain visible when chroma is softened.
12. Confirm post overflow, long names and missing payloads fail safely without shrinking type or exposing raw URLs.
13. Confirm only one row moves; measure crawl/pagination comprehension at 480p and revise cadence.
14. Inspect wipes frame by frame for incomplete cover, matte fringing, banding and a visible host-chain discontinuity.
15. Listen for pumping, clipped stings and speech masking; tune ducking beyond the 100/600 ms starting values.
16. Check player controls against bug, ticker and sponsor placement; remove any unique fact from covered regions.
17. Lock pixel/timing values only after the test capture, recording the accepted OBS profile, bitrate, frame rate and rendition.
