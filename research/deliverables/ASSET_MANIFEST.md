# Asset deliverable manifest

Hand this file and [DESIGN_BRIEF.md](DESIGN_BRIEF.md) to a design agent. They implement Package A. Package B can ride along or follow.

**Relocked 2026-09-01.** [RELOCK_PROPOSAL.md](RELOCK_PROPOSAL.md) is the accepted decision record; this manifest contains the resulting production contract.

Ship into `assets/broadcast/` exactly as named. Do not invent a parallel tree. Preview work may live under `research/mocks/` until accepted.

All rectangles are 1920×1080, origin top-left. Values marked **lock** are project-locked. Values marked **rev** replace a provisional spec number — use the revision.

## Locked tokens

| Token | Value | Status |
| --- | --- | --- |
| `foundation` | `#0B0A08` | lock |
| `plate` | `#15130F` at 93% | lock; essential type still meets ≥7:1 |
| `text-primary` | `#F4F1EA` | lock |
| `text-secondary` | `#ADA69A` | lock |
| `jade` | `#14B87A` | programme accent; desk rule and kicker chip only |
| `live` | `#E2543F` | 10 px LIVE dot only |
| `gain` | `#A3BE9C` | with `▲` and a numeric sign |
| `loss` | `#D89A88` | with `▼` and a numeric sign |
| `rule-essential` | 4 px | lock |
| `radius-max` | 8 px | lock |
| `skew` | 0° | lock |
| `glow` | none | lock |
| Display face | Archivo 600–800, variable `wdth` 62–125 | vendor OFL |
| Data face | Inter 600 / 700 + `tnum` | vendor OFL |
| System face | JetBrains Mono 500 | vendor OFL |

Essential type ≥ 26 px. Contrast of essential text on its plate ≥ 7:1. No text below 500 weight.

## Geometry lock (`split`)

| Element | x | y | w | h | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| `HOST_CROP_L` | 64 | 140 | 580 | 660 | 50% of 1344×768, cover-scaled. |
| `CENTER_CARD` | 668 | 140 | 584 | 660 | 24 px gutters from both host wells. |
| `HOST_CROP_R` | 1276 | 140 | 580 | 660 | Same source, other half. |
| `SYSTEM_RAIL` | 64 | 48 | 1792 | 60 | Mark, LIVE, segment, clock and sponsor share one rail. |
| `CHYRON` | 64 | 838 | 1792 | 118 | Kicker chip plus land. |
| `TICKER` | 64 | 972 | 1792 | 56 | One row. |

Host IDs attach to the aperture. The active host's name plate inverts; there are no host frames or `ON AIR` tabs. Do not place a unique fact in y > 1026 (player chrome).

768p cover into a well: scale half-frame 672×768 by `max(580/672, 660/768)` = 0.863, then crop the horizontal excess. Do not let a compositor letterbox or stretch.

## Package A — identity + live CG (design now)

Every item is a file you hand back. HTML/CSS is the production medium. A Figma page is optional and not a substitute.

| ID | Deliverable | Format | Spec |
| --- | --- | --- | --- |
| A1a | `assets/broadcast/fonts/Archivo-Variable.ttf` | TTF | Weights 600–800; width axis 62–125. Include `OFL.txt`. |
| A1b | `assets/broadcast/fonts/JetBrainsMono-Medium.ttf` | TTF | Weight 500. Include `OFL.txt`. |
| A2 | `assets/broadcast/fonts/Inter-SemiBold.ttf` | TTF | Weight 600, tabular nums verified in a browser. Include `OFL.txt`. |
| A3 | `assets/broadcast/fonts/Inter-Bold.ttf` | TTF | Weight 700, `tnum`. |
| A4 | `assets/broadcast/tokens.css` | CSS | Custom properties for every token in the table above. No extra colours. |
| A5 | `assets/broadcast/bug/show-bug.svg` | SVG | 72×72 viewBox. Original mark. High contrast on `foundation`. No letters that have to be regenerated. Also export `show-bug.png` @1x. |
| A6 | `assets/broadcast/overlay/index.html` | HTML | 1920×1080. Transparent `body` when `hold: false`. One root that binds [overlay-state.schema.json](overlay-state.schema.json). |
| A7 | `assets/broadcast/overlay/app.js` | JS | Poll or accept injected state. Default `hold: false`. Clock ticks locally if `clock` omitted. |
| A8 | `assets/broadcast/overlay/style.css` | CSS | Imports `tokens.css` + local `@font-face`. Implements every template in the table below. |

### Overlay templates (A6–A8 must include all)

| Template | Type | Copy | Motion |
| --- | --- | --- | --- |
| `SHOW_BUG` | persistent in rail | accepted two-mass mark | none on topic change |
| `LIVE_BADGE` | persistent in rail | `LIVE` JetBrains Mono 500 / 30 px + 10 px `live` dot | none |
| `CLOCK` | persistent in rail | `HH:MM:SS` JetBrains Mono 500 / 30 / `tnum` | digits only |
| `SPONSOR_CELL` | right side of rail | `PRESENTED BY` JetBrains Mono 500 / ≥26 + name | hold 8–12 s; never crawl |
| `SPEAKER_STATE` | attached to host ID | active host-name plate inverts to ink on bone and carries the live cursor | exactly one inverted plate when speaker is known; none when unknown |
| `HOST_ID_L/R` | attached | `PHASEONE[lol]` / `deb` Archivo 700 / 40. Axis/handle JetBrains Mono 500 / 22–28 | 5–7 s first show. Exact case. No `text-transform: uppercase` on `deb`. |
| `CENTER_CARD` / **post** | payload | kicker ≤12, author ≤48, body ≤240 chars / 8 lines | plate swap only; shell never moves |
| `CHYRON` | bottom | kicker ≤12 uppercase Archivo 700 / 28; headline ≤90 Archivo 700 / 42, ≤2 lines, sentence case | replace copy under a stationary plate |
| `TICKER` | bottom | paginated 6–8 s; one symbol/value/`▲` or one short sentence | one moving row |
| `HOLD` | z=100 | brand + `STAND BY` | **off** unless `hold: true` |

M0 card payload is **post** only. Leave `chart` / `image` / `guest` / `error` as empty shells that fail safe (solid plate, short status, no raw URL).

### Copy rules the designer must enforce in the templates

1. Overflow: edit → wrap → ellipsis. Never shrink below 26 px.
2. Chyron is the land. If headline ≈ card body, the template is being fed a reject. Still render; do not “fix” by shrinking.
3. Gain/loss: `▲ +0.80` / `▼ −0.22` plus colour. Render a sign only when a numeric `value` or `change` exists; sentence items have no sign. Never colour alone.
4. No avatars, tweet chrome, or live-fetched images in the post card.

## Package B — baked motion and audio (same cadence, can follow)

No readable type in any generated or illustrated plate. Overlay sets titles on the hold frames.

| ID | File | Duration | Picture | Sound |
| --- | --- | --- | --- | --- |
| B1 | `assets/broadcast/stingers/utility_080.webm` | 0.80 s / 24f @30 | Combined overlay+matte. Cover by frame 12. Horizontal sweep, coarse blocks. | Noise impulse + short button |
| B2 | `assets/broadcast/stingers/utility_120.webm` | 1.20 s | Same geometry, more hold | same |
| B3 | `assets/broadcast/bumpers/sting_03.webm` | 3.0 s | Title-safe hold last 0.45–0.60 s | resolved |
| B4 | `assets/broadcast/bumpers/segment_05.webm` | 5.0 s | Title hold last 0.75–1.0 s | out resolved; in unresolved |
| B5 | `assets/broadcast/bumpers/open_10.webm` | 10.0 s | Show start only | cold open |
| B6 | `assets/broadcast/audio/bed_loop.wav` | 30–60 s seamless | — | sparse; duck 100/600 ms start |
| B7 | matching wipe/sting/bumper stems | match picture | — | full mix + percussion + motif + button + bed |

Prompt-safe plates only. One family. Do not replay `open_10` between topics.

## First fixture (must render)

Feed [fixtures/segment-20260831T154227Z.json](fixtures/segment-20260831T154227Z.json) `overlay` into A6.

Acceptance stills the design agent must attach:

1. `split` + BOT1 active plate + post card + land chyron + ticker.
2. Same, BOT2 active plate (inversion moves to the other name).
3. `hold: true` (desk gone, furniture optional).
4. 480p downscale of still 1 at 100% crop on the chyron and on `PHASEONE[lol]`.

A compositor that puts the real 10.4 s two-shot under these plates is in [../mocks/composite_segment_through_cg.py](../mocks/composite_segment_through_cg.py). Use it. Do not regenerate the hosts.

## Acceptance (fail any → not done)

- [ ] Vendored fonts + OFL, no production CDN.
- [ ] Tokens file has no undeclared colour.
- [ ] Bug is original and legible at 72×72 and at 32×32.
- [ ] Overlay body is transparent when not holding.
- [ ] Sponsor is right-aligned in the system rail at a 64 px inset and never overlaps a host well.
- [ ] `deb` is not forced uppercase.
- [ ] Exactly one host-name plate is inverted whenever a speaker is set; none is inverted when unknown.
- [ ] Card body that exceeds 240 chars ellipsizes; type size unchanged.
- [ ] Fixture land paints; fixture `rejected_package_chyron` is not used.
- [ ] No named-show language in any asset.
- [ ] Still 1 survives a 480p (`scale=854:480`) read of names, land, and `▲/▼`.
- [ ] No textural cell is below 20 px for ASCII or 8 px for mosaic/Bayer; host-visible texture is static.

## Out of scope

ATEM/vMix/Teradek. Ross/Chyron. Host/hero generation. Writer prompts. Chat chrome. Guest card. Chart plot. Ad-read stills. Any future relock without an explicit decision record.
