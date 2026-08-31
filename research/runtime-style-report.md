# Runtime visual system — production synthesis

This report merges the six research lanes into one direction for M0. It does not replace the [architecture](../Desk%20Show%20%E2%80%94%20Two-Host%20Architecture%20%26%20Harness.md) or [character and set bible](../Desk%20Show%20%E2%80%94%20Character%20%26%20Set%20Bible.md); `studio.yaml` remains the generated-frame source of truth and the [graphics spec](runtime-graphics-spec.md) governs OBS.

## Executive direction

Runtime should look like a stable, legible broadcast occupying a tactile but restrained converted-office set. The generated layer supplies two original, silhouette-led cartoon robots and coarse scenic depth. The deterministic OBS layer supplies every word, frame, state, card and transition.

The hierarchy is binding:

1. Opaque OBS host boxes and the centre card dominate.
2. Generated scenic richness is confined to coarse shapes in the outer thirds; the centre is neutral and dark.
3. The picture is stable by default. Sparse, broad horizontal signal faults punctuate transitions rather than continuously degrading the image.
4. Identity survives without colour: PHASEONE[lol] is dark, broad and low; deb is light, tall and narrow. Amber and cyan/teal are accents, never dominant shells.

## Evidence, decisions and hypotheses

**Evidence from retrieved sources**

- Reduced faces can carry acting through eye geometry, head tilt and gross body shape; clean contours, flat fields and selective movement also support limited animation ([L1](findings/L1-character-design.md); [Robot Dreams interview](https://www.hollywoodreporter.com/movies/movie-features/robot-dreams-director-interview-simplicity-characters-friendship-1235828307/); [MiRAE study](https://www.caseybennett.com/uploads/MiRAE_Paper_Final.pdf)).
- Small studios gain depth from talent/background separation, oblique planes, motivated practicals and back/rim light ([L2](findings/L2-set-design.md); [small-studio guidance](https://tvsetdesigns.com/blogs/news/developing-a-small-tv-studio-design); [Rosco lighting guide](https://spectrum.rosco.com/the-basics-of-film-lighting)).
- Broadcast systems remain coherent through shared templates, grids, tokens and responsive text regions ([L3](findings/L3-broadcast-graphics.md); [MLB Network package](https://www.rcs.live/work/mlb-network-rebrand); [Worlds modular grid](https://buck.co/work/riot-games-world-championships)).
- Real multibox systems preserve source framing and attach metadata/state to apertures independently of layout ([L4](findings/L4-multibox-layouts.md); [mimoLive split-screen controls](https://mimolive.com/user-manual/live-editing/layers/layout/splitscreen/)).
- Barlow Condensed and Inter are OFL-licensed; SIL explicitly permits video titling. W3C requires adequate contrast and redundant non-colour state cues ([L5](findings/L5-type-color.md); [OFL FAQ](https://software.sil.org/downloads/r/oflt/OFL-FAQ.txt); [W3C contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum)).
- OBS supports deterministic track-matte stingers and recommends 100 ms attack / 600 ms release as sidechain-ducking starting points ([L6](findings/L6-motion-idents.md); [OBS stingers](https://obsproject.com/kb/track-matte-stinger-transitions); [OBS compressor](https://obsproject.com/kb/compressor-filter)).

**Runtime design decisions**

- Two mouthless hosts use five identity anchors: head silhouette, shoulder-width category, face-panel shape, eye arrangement and dominant shell value.
- Host crops retain one internal transform throughout multibox layouts; apertures translate. A separate full-wide source item handles the establishing view.
- The source join is never exposed as a one-pixel seam. Apertures overlap beneath an opaque 8 px divider or the centre card.
- Furniture is charcoal/off-white with amber and teal accents. Gains and losses use sign and shape as well as muted colour.
- Essential rules start at 3–4 px at 1080p. Host/card borders are opaque 8 px, corners are at most 8 px, and the system uses no glow or skew.
- Barlow Condensed serves short editorial display; Inter serves body, metadata and tabular data.

**Hypotheses requiring encode tests**

- A 26 px minimum for essential type, a 96 px horizontal title inset, the proposed ticker cadence and all exact pixel geometry are conservative starting points, not sourced Twitch standards.
- Utility transitions should land around 0.8–1.2 seconds, but exact cut frames must be selected after OBS-to-Twitch encoding tests.
- 480p generation may be acceptable in the split layout but fail in `wide`; E7 must test both.

## Adopt, reject, validate later

| Status | Direction | Basis |
| --- | --- | --- |
| Adopt | Flat fields, heavy uniform contours, few expressive degrees of freedom | Retrieved character/limited-animation evidence; drift requirement |
| Adopt | Dark/broad/low BOT1 versus light/tall/narrow BOT2 | Runtime identity decision supported by silhouette evidence |
| Adopt | Motivated warm-left/cool-right accents plus neutral rim separation | Retrieved lighting practice; Runtime adaptation |
| Adopt | Coarse outer-third set dressing and a quiet dark centre | Small-studio/set evidence reconciled with centre-card needs |
| Adopt | Opaque modular OBS furniture, 8 px borders, ≤8 px radius, no skew/glow | Compression-safe Runtime decision |
| Adopt | Barlow Condensed + Inter, bundled with OFL files | Retrieved licensing evidence |
| Adopt | Stable baseline; sparse horizontal signal faults | Retrieved title-design logic; Runtime drift strategy |
| Reject | Hairlines, RGB masks, fine scanlines, microtype, tiny wear and gradients | Downscale/chroma risk; no operational benefit |
| Reject | Hinged jaws, waveform/equalizer mouths, dense seams, rivets and readable generated displays | Drift and text-flicker risk |
| Reject | Audio-driven resizing, internally rescaled host crops and payload-specific outer layouts | Shared-source geometry and continuity |
| Reject | Teal/orange shell fills or room-wide colour washes | Silhouette/value separation must not depend on local light |
| Validate later | Exact type minima, safe area, ticker rate, dwell and transition frames | No retrieved source establishes Runtime/Twitch-specific thresholds |
| Validate later | 480p generation and `tnum` support in the target OBS browser renderer | Renderer and encode-path dependent |

## Original character system

PHASEONE[lol] is a mouthless, low rounded-box head over broad sloping shoulders and a bottom-heavy torso. Its dominant shell is dark charcoal; two large amber round lenses and one thick amber key are the only warm accents. Thick brow plates, pupil direction and whole-head tilt supply expression. Its upright, low-motion posture reads dry and controlled.

deb is a mouthless, tall clipped-capsule head over narrow square shoulders and a slim torso. Its dominant shell is matte off-white; a broad dark visor holds two large cyan eye blocks. Eye height, pupil direction and head lean supply expression. A plain dark hoodie and broad backward cap support the tall silhouette; forward posture and block-like gestures read restless.

The model may vary minor secondary proportions, but not either host's five identity anchors. No jaw, waveform, antenna, tiny controls, fingers, reflective glass or fine seams should become identity-bearing.

## Set

A matte pale-grey desk spans the lower third with a deliberately empty centre. Chunky microphones enter from the outer edges. The far-left and far-right bays contain only a few large objects: deep-bodied blank tube monitors, broad plywood returns, a concrete column, dark acoustic curtains and heavy cable loops. Monitor faces carry dim fields, soft static masses or broad glow bands—never text or diagrams.

An amber task lamp motivates restrained warm light at left; blank blue-green monitor glass motivates restrained cool light at right. Both hosts receive neutral rim separation. BOT1's dark shell must remain distinct from its background; deb's light shell must remain distinct from the cool key. The middle is matte charcoal, low-contrast and screen-free.

## Deterministic broadcast graphics

OBS owns the bug, LIVE badge, clock, host IDs, speaking state, headline chyron, ticker, sponsor slot, centre-card shell and transitions. Components share a 4/8/16 px spacing rhythm, opaque neutral plates, squared geometry and one data model. Copy reflows within bounded templates; it is edited or ellipsized before type shrinks below the tested minimum. See the [runtime graphics spec](runtime-graphics-spec.md).

## Multibox layout

The signature layout uses two fixed 620×700 host apertures and one 600×700 centre card on a 1920×1080 canvas. Guest, chart, image and post payloads change only inside the centre shell. Guest video may cover; informational payloads contain. When the card is absent, the fixed host apertures may move together, but an opaque divider or overlap treatment still hides the source split. Wide view uses the dedicated full-source item rather than changing the crop transforms.

Speaker state is a thick border plus attached solid state tab; it never zooms a host. The centre becomes primary through its solid plate and, if necessary, a modest host dim—not through rearranging or rescaling the sources.

## Type and palette

- **Display:** Barlow Condensed 700 for short names, kickers and editorial headlines.
- **Data/body:** Inter 600–700, with verified tabular numerals for clocks and values.
- **Foundation:** `#101116`; raised plate `#171A20`; primary `#F2F0E8`; secondary `#A9ADB7`.
- **Accents:** amber `#F2A541`; teal `#2FB7B2`.
- **State:** gain `#4FC58B`; loss `#E05D68`, always paired with `+`/`−` and ▲/▼ or another shape.

All essential copy sits on an opaque plate. Accent colour groups and signals; neutral luminance carries readability.

## Motion and audio vocabulary

The visual verb is **acquire → lock → brief fault → resync**. Motion travels horizontally or on an orthogonal block grid. Utility wipes fully occlude the programme once and begin from a provisional 0.8–1.2 second family. Longer 3/5/10 second units reuse the same broad sweep, geometric lock and calm final hold. There are no diagonal turbulence, particles, RGB splits, looping glitches or fine scanlines.

The sonic verb is **relay click → rising two-note pulse → low resolved button**. Resolved stings close a segment; unresolved links return to the bed. Print full mix, noise/percussion, tonal motif, button and bed stems. OBS's 100 ms attack and 600 ms release are initial sidechain settings only; loudness, threshold and gain reduction require a recorded mix test.

## Conflicts resolved

- **Rich set versus readable boxes:** boxes and card win; scenic richness moves outward and becomes coarse.
- **Continuous source versus separated panes:** preserve crop continuity, but conceal the join with overlap, an opaque divider or card.
- **Expressive mouths versus drift:** eyes, brows, head posture and speaker furniture replace jaws and fine display mouths.
- **Warm/cool identity versus value stability:** shell value and silhouette identify hosts; amber/teal merely reinforce them.
- **Retro-computer texture versus Twitch delivery:** large raster bands and block faults replace masks, scanlines, microtype and dither.
- **Energetic motion versus conversational utility:** expressive motion is reserved for stings; everyday graphics settle quickly and remain still.

## Source limitations

No retrieved source establishes a universal Twitch title-safe rectangle, minimum font size, ticker speed, Runtime-specific dwell time or precise transition duration. Several media-heavy or authenticated galleries could not be inspected; the lane reports identify those exclusions. Desktop finance references demonstrate hierarchy and alignment, not broadcast-scale density. Traditional model sheets are only an analogue for generative drift. Exact 480p survival, chroma behaviour, font-feature support and generated-character continuity remain empirical questions.

## M0 approval checks

Approve only when all checks pass:

1. **Prompt audit:** no named IP/style reference and no request for readable generated text.
2. **Split crop:** each host remains complete in its half and clear of the centre-card occlusion.
3. **Identity/squint:** grayscale blur still reads BOT1 as dark/broad/low and BOT2 as light/tall/narrow.
4. **Value separation:** warm light does not swallow BOT1; cool light does not flatten deb; both retain a neutral rim edge.
5. **Set hierarchy:** coarse richness stays in the outer thirds; centre is dark, neutral and quiet.
6. **Detail audit:** no jaw, waveform/equalizer, tiny rivets/cards/text, dense seams, thin monitor marks or generated readable graphics.
7. **Rest frame:** neutral expression, mouthless faces, no mid-gesture pose, stable headroom.
8. **OBS geometry:** crop sync verified; host transforms fixed; join fully hidden; card and 8 px borders align.
9. **Encode ladder:** capture native 1080, Twitch-like encode and 480p playback; verify type, borders, state cues, ticker and motion using the graphics-spec checklist.
10. **E7 decision:** explicitly approve or reject 480p generation in both `split` and `wide`; do not infer one from the other.
