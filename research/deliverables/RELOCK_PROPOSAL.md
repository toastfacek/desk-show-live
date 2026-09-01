# Relock decision record — Package A token and geometry table

**Status: accepted on 2026-09-01 for Package A.** Sections 1–5, the two-host desk mark, and the revised acceptance checklist are the production direction. Programme accent amended 2026-09-01 from `jade` `#14B87A` to `lemon` `#D4E04A` so the desk rule does not read as TBPN green.

[ASSET_MANIFEST.md](ASSET_MANIFEST.md) puts *"relocking the graphics spec"* out of scope and asks instead that collisions be reported rather than silently forked. The design work in [../mocks/identity-bracket.html](../mocks/identity-bracket.html) has reached a coherent system that departs from the locked table in about fifteen places. Shipping it into `assets/broadcast/` without this document would be that silent fork.

This record preserves every departure, what it replaces, and why. Package A is cut against the right-hand column. The authoritative file contract and pixel grammar have been updated in [ASSET_MANIFEST.md](ASSET_MANIFEST.md) and [../runtime-graphics-spec.md](../runtime-graphics-spec.md).

Three things did **not** change and are not up for discussion here: the 26 px essential-type floor, the ≥7:1 contrast requirement on essential text, and the rule that no text is ever baked into a generated frame.

## Decision summary

- **Accepted:** the warm espresso colour system in §1, with `lemon` `#D4E04A` as the programme accent.
- **Accepted:** the floating 64 px geometry and unified top rail in §2.
- **Accepted:** inverted host-name plates as the sole speaker-state signal in §3.
- **Accepted:** Archivo for display, Inter for data, and JetBrains Mono 500 for system text in §4.
- **Accepted with an operational gate:** the coarse code layer in §5. It ships static when hosts are visible; moving texture stays behind a flag until a received Twitch rendition passes the encode test.
- **Accepted:** the current two-mass mark, derived from the two hosts and shared desk rule, for Package A5.

---

## 1. Colour

| Token | Locked | Proposed | Why |
| --- | --- | --- | --- |
| `foundation` | `#101116` | `#0B0A08` | The locked value is a blue-black. The set is walnut, cream and forest green under warm even light, and a cool slab over a warm room reads as a cheaper layer added in post. Espresso is pulled from the set's own walnut. |
| `plate` | `#171A20` | `#15130F` at 93% | Same hue correction. The 7% transparency is indistinguishable from opaque for legibility and completely different for depth — the room is faintly present behind the panel. |
| `idle-frame` | `#2A2E38` | **removed** | There are no borders. A dark panel on a bright room needs none, and the frame's whole job was separating a panel from a picture it now separates itself from by value. |
| `text-primary` | `#F2F0E8` | `#F4F1EA` | Warmer by a hair, to sit with the cream set. **16.5:1** on panel. |
| `text-secondary` | `#A9ADB7` | `#ADA69A` | Warm neutral rather than cool. **7.7:1** on panel. |
| `amber` | `#F2A541` | **removed as a speaker accent** | See §3. Speaker state no longer uses hue at all. |
| `teal` | `#2FB7B2` | **removed as a speaker accent** | Same. This also retires the cobalt-versus-teal collision rather than settling it. |
| `gain` | `#4FC58B` | `#A3BE9C` | Desaturated so it never competes with the one saturated colour. **8.5:1** on panel. Still always with `▲` and a sign. |
| `loss` | `#E05D68` | `#D89A88` | Same. **7.2:1** on panel. |
| — | — | `lemon` `#D4E04A` | **Amended.** Was `jade` `#14B87A`. Jade read as TBPN green on air. Acid lemon is the one saturated colour, in the desk rule and kicker chip. Amber would still read as PHASEONE[lol], blue as deb. Ink type on the chip. |
| — | — | `live` `#E2543F` | **New.** A 10 px dot beside `LIVE`, and nothing else. Non-text, so its 4.5:1 is not a type contrast. |

**Net:** one saturated colour on the furniture instead of four, and the room carries the rest.

## 2. Geometry

Everything floats on a 64 px margin rather than bleeding to the frame edge. That single change is the largest visual difference and it costs nothing but coordinates.

| Element | Locked | Proposed |
| --- | --- | --- |
| `HOST_CROP_L` | `40,100,620×700` | `64,140,580×660` |
| `CENTER_CARD` | `660,100,600×700` | `668,140,584×660` |
| `HOST_CROP_R` | `1260,100,620×700` | `1276,140,580×660` |
| `SHOW_BUG` | `96,54,72×72` | folded into the system rail at `64,48`, h 60 |
| `LIVE_BADGE` | `1584,54,112×40` | into the same rail |
| `CLOCK` | `1704,54,120×40` | into the same rail |
| `SPONSOR_CELL` | `184,70,220×40` (rev) | right-aligned, 64 px inset, `y=48`, h 60 |
| `CHYRON` | `0,900,1920×96` | `64,838,1792×118` |
| `TICKER` | `0,996,1920×52` | `64,972,1792×56` |
| Cover transform | 0.9226 from 672×768 | **0.863** — the wells are 580×660, not 620×700 |

The bug, LIVE, segment counter and clock collapse from four scattered rectangles into one lockup. That incidentally retires collision 5 from the first pass: with no separate bug rectangle and no speaker tab, the 66 × 18 px overlap cannot occur.

`radius-max` is **unchanged and now under-used** — it locks 8 px as a maximum and the package uses 0. `skew` stays 0°, `glow` stays none. **No locked geometry token is exceeded by this proposal.**

Unchanged: nothing unique lives below `y=1026`, where player chrome sits.

## 3. Speaker state — the one behavioural change

| Locked | Proposed |
| --- | --- |
| 8 px frame goes `amber` or `teal`; a solid `ON AIR` lozenge is mandatory redundancy because colour alone is a fail | The live host's **name plate inverts** to ink on bone. No frame, no tab, no accent. |

The locked design is correct about the problem and expensive about the solution: amber and teal sit about 1.2:1 apart in luminance, so the tab exists to prop up a signal that colour cannot carry alone.

Inversion replaces hue with **value**, which survives grayscale, every form of colour-vision deficiency and any amount of chroma softening without a second element propping it up. At **17.5:1** it is the highest-contrast element on the canvas, so the thing the eye should find first is the thing it does find first — and in a 480p read the state difference becomes *more* obvious as resolution drops, not less.

The live plate also carries a small cursor, the same mark that follows the wordmark on air, so "live" is one shape wherever it appears.

## 4. Type

| Role | Locked | Proposed |
| --- | --- | --- |
| Display | Barlow Condensed 700 | **Archivo** 600–800, variable `wdth` 62–125 |
| Data | Inter 600/700 + `tnum` | unchanged |
| System | — | **JetBrains Mono** 500 — status, clocks, symbols, labels |

Archivo was already named in [../findings/L5-type-color.md](../findings/L5-type-color.md) as the best single-family route: one variable grotesque, OFL, cleared for video titling. Its width axis means **copy is fitted by width rather than by size**, which makes the "never shrink below 26 px" rule far easier to hold. All three are OFL and vendored; the CDN links in the mocks are preview only.

Mono never takes a headline, a card body or a host name — at 44 px it is a terminal, which is the thing the design is escaping.

## 5. New section — the code layer

Not in the locked spec at all, so this is an addition rather than a departure. The graphics spec bans dither by name and is **right for fine dither**: high-frequency noise is the most expensive thing you can hand a video encoder, stealing bitrate from the hosts' faces and crawling between frames. Coarse dither is a different object. Proposed rules:

- **Cell floors.** Nothing textural below **20 px** at 1080 (the mono cell). No mosaic or Bayer cell below **8 px**.
- **Two placements.** A **ground wash** at z=0 runs permanently, including on air; it is visible only in margins and gutters (about 27% of the canvas) because the host wells are opaque picture and the panels are 93%. A **field**, where texture is the subject of the frame, stays in host-free states: hold, error card, bumpers, cold open.
- **Never behind essential type.** On the ground layer this is guaranteed by z-order rather than by discipline.
- **Motion is the real gate, not detail.** A static pattern encodes once into a reference frame and then costs almost nothing; a moving one cannot be held in reference and pays every frame. So the wash is **static whenever a host is on screen**, and drift is reserved for host-free states with a cycle measured in tens of seconds.
- Whether a slow drift is affordable on air is a question for the encode ladder, not for a simulation. Ship static; test drift behind a flag.

ASCII is treated as type, not texture, which is why it rides the encode ladder essential type already passed.

## 6. Acceptance checklist — revised

Lines that survive unchanged from the manifest are marked ⟢. Lines that change are marked ⟡ with the reason.

- ⟢ Vendored fonts + OFL, no production CDN.
- ⟢ Tokens file has no undeclared colour.
- ⟢ Bug is original and legible at 72×72 and at 32×32.
- ⟢ Overlay body is transparent when not holding.
- ⟢ `deb` is not forced uppercase.
- ⟢ Card body over 240 chars ellipsizes; type size unchanged.
- ⟢ Fixture land paints; `rejected_package_chyron` is not used.
- ⟢ No named-show language in any asset.
- ⟢ Still 1 survives a 480p read of names, land and `▲/▼`.
- ⟡ ~~Sponsor sits at `184,70`~~ → **Sponsor sits in the top rail, right-aligned at a 64 px inset, and never overlaps a host well.**
- ⟡ ~~Idle frames visible (`#2A2E38` 8 px)~~ → **No frames. The idle host's name plate is legible against the picture at ≥7:1.**
- ⟡ ~~One `ON AIR` tab maximum; tab present whenever a speaker is set~~ → **Exactly one host plate is inverted whenever a speaker is set, and none when the speaker is unknown. State is legible in grayscale with no colour information at all.**
- ⟡ **New:** no textural cell below 20 px (ASCII) or 8 px (mosaic/Bayer); no field in any frame containing a host.

---

## Implementation impact

The decisions are resolved. This table records which accepted section each deliverable now implements.

| Deliverable | Implements | Production direction |
| --- | --- | --- |
| `A1a–A1b` display/system fonts | **§4** | Vendor Archivo variable plus JetBrains Mono 500 and their OFL files. |
| `A2`, `A3` Inter | **§4** | Retain Inter for data and tabular numerals. |
| `A4` tokens.css | **§1** | Use the accepted warm-neutral table with lemon and live tokens. |
| `A5` show-bug.svg | **mark decision** | Promote the two-mass mark from [../mocks/mark/](../mocks/mark/). |
| `A6` overlay/index.html | **§2** | Implement the floating 64 px grid and unified rail. |
| `A7` app.js | **§3** | Drive exactly one inverted host-name plate when a speaker is known. |
| `A8` style.css | **§1 §2 §3 §4 §5** | Implement the accepted system; keep on-air texture static. |

Package B is unaffected — it is a motion and audio cadence, and nothing in it depends on the colour table.

## Collision resolution

| # | Collision | Status |
| --- | --- | --- |
| 2 | Sponsor rev at `184,70` crosses the left well's top border by 10 px | **Closed by §2** — sponsor content lives in the unified rail, right-aligned at a 64 px inset. |
| 4 | Sentence ticker items can carry a `sign` without a `value` | **Closed** — render a sign only when a numeric `value` or `change` is present; sentence items render without a sign. |
