# Relock proposal — Package A token and geometry table

**Status: proposal. Nothing ships against it until it is signed off.**

[ASSET_MANIFEST.md](ASSET_MANIFEST.md) puts *"relocking the graphics spec"* out of scope and asks instead that collisions be reported rather than silently forked. The design work in [../mocks/identity-bracket.html](../mocks/identity-bracket.html) has reached a coherent system that departs from the locked table in about fifteen places. Shipping it into `assets/broadcast/` without this document would be that silent fork.

So this is the report. Every departure, what it replaces, and why. Approve it and Package A can be cut against the right-hand column; reject any line and the design returns to the left.

Three things did **not** change and are not up for discussion here: the 26 px essential-type floor, the ≥7:1 contrast requirement on essential text, and the rule that no text is ever baked into a generated frame.

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
| — | — | `jade` `#14B87A` | **New.** The one saturated colour, in exactly two placements that mean the same thing: the desk rule in the mark, and the kicker chip in the chyron and centre card. Pulled from the set's forest-green pillars. Neither host owns green — amber would read as PHASEONE[lol], blue as deb — so it reads as the programme rather than a person. **7.7:1** on ground, **7.3:1** on panel, with ink type on the chip. |
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
| System | — | **JetBrains Mono** 400/500 — status, clocks, symbols, labels |

Archivo was already named in [../findings/L5-type-color.md](../findings/L5-type-color.md) as the best single-family route: one variable grotesque, OFL, cleared for video titling. Its width axis means **copy is fitted by width rather than by size**, which makes the "never shrink below 26 px" rule far easier to hold. All three are OFL and vendored; the CDN links in the mocks are preview only.

Mono never takes a headline, a card body or a host name — at 44 px it is a terminal, which is the thing the design is escaping.

## 5. New section — the code layer

Not in the locked spec at all, so this is an addition rather than a departure. The graphics spec bans dither by name and is **right for fine dither**: high-frequency noise is the most expensive thing you can hand a video encoder, stealing bitrate from the hosts' faces and crawling between frames. Coarse dither is a different object. Proposed rules:

- **Cell floors.** Nothing textural below **20 px** at 1080 (the mono cell). No mosaic or Bayer cell below **8 px**.
- **Fields only where no host is on screen** — hold, error card, bumpers, cold open — because that is where bitrate is not being spent on faces. On-air furniture gets a single row at most.
- **Never behind essential type.** Texture and copy take turns.
- **Motion is a second gate.** A moving field cannot be held in reference, so drift is confined to the same host-free states, with a cycle measured in tens of seconds.

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

## What is blocked on this

`A4 tokens.css` cannot be written against two different colour tables, and `A5`–`A8` all import it. So Package A is blocked on §1 and §2 specifically; §3–§5 can be argued separately without holding up the build.

The mark itself is not blocked — it uses `bone` and `jade` only, and preview cuts are in [../mocks/mark/](../mocks/mark/) pending sign-off.

## What is still open from the first pass

| # | Collision | Status |
| --- | --- | --- |
| 2 | Sponsor rev at `184,70` still crosses the left well's top border by 10 px | **Open**, and moot if §2 is approved — the rail has no overlap at all |
| 4 | Fixture ships sentence ticker items carrying a `sign` but no `value`, producing an arrow pointing at nothing | **Open** — honour `sign` only alongside a `value` or `change`. One condition in the ticker renderer, independent of everything above |
