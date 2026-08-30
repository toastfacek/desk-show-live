# L4 — Multibox layouts

## Top picks

### CNBC 2014 on-air redesign
- **Source:** https://www.brainstorm3d.com/wp-content/uploads/2020/03/CS_CNBC_2015.pdf
- **Steal:** Keep live talent present while a half-screen information format comes and goes, using the content panel itself as the transition rather than cutting to a wholly different composition.
- **Why it serves Runtime:** The source explicitly describes fluid integration of live video, interviews, talent, and data, plus a half-screen data format that can appear as needed. **My inference for Runtime:** build two stable host wells and one typed centre well; a guest, chart, static image, or tweet changes only the centre well's inner template, never the outer geometry. Use a fixed 600×700 centre card with a roughly 552×620 safe interior: portrait guest video may crop to fill, while charts, images, and tweet cards fit within that interior on a solid plate. This preserves legibility at 480p and keeps all readable text in OBS.

### ESPN Goodyear BlimpCast
- **Source:** https://awfulannouncing.com/espn/espn-brings-the-megacast-including-blimpcast-to-labor-day-matchup-between-florida-state-and-virginia-tech.html
- **Steal:** Give one box a clearly dominant editorial role and use the other two as reaction or context boxes instead of treating all three feeds equally.
- **Why it serves Runtime:** The retrieved article describes an actual three-box presentation: the normal game view holds most of the screen, with a smaller host view and a third aerial view; its embedded ESPN PR post also supplies a real visual example. **My inference for Runtime:** when the centre contains a chart or tweet, it is the dominant reading target even if its pixel area is similar to the hosts; lower host contrast slightly and give the centre card the brightest solid plate. When the centre is a guest, restore equal contrast so the result reads as a three-person panel.

### ESPN NCAA wrestling split screen
- **Source:** https://www.sportsvideo.org/2010/03/17/espn-splits-its-screen-for-wrestling-coverage/
- **Steal:** Treat the boxes and their attached metadata as one responsive unit, with tested stacked or staggered variants and horizontally elongated HD-safe apertures.
- **Why it serves Runtime:** This is a documented real broadcast in which creative services supplied a two-box graphic, operators could choose stacked or staggered arrangements, and each score unit shrank and realigned with its video. **My inference for Runtime:** names and speaker state should remain physically attached to each host well, while the global ticker stays independent. Use 8 px opaque borders at 1080p, no glow, and a small solid corner/name tab for state; those shapes remain readable after Twitch compression and downscaling.

### ESPN High Noon boxed combinations
- **Source:** https://www.sportsvideo.org/2018/06/13/espns-high-noon-innovates-with-24-fps-letterbox/
- **Steal:** Use simultaneous views to show the listener as well as the speaker, but constrain the show to a small rehearsed family of box geometries.
- **Why it serves Runtime:** The production used split and quad views to preserve visible listening reactions and reported testing 70 boxed combinations, with 47 used; it also used shallow depth and clean fall-off to pull people forward. **My inference for Runtime:** the valuable idea is reaction visibility, not combinatorial variety. Runtime needs only three presets: paired hosts, host–content–host, and host–guest–host. Keep host crop, scale, border, and lower-third anchor unchanged across all three.

### mimoLive Split Screen Layer
- **Source:** https://mimolive.com/user-manual/live-editing/layers/layout/splitscreen/
- **Steal:** Define each source by explicit centre/size geometry, preserve per-source pan/tilt/zoom, and express speaker state independently from layout state.
- **Why it serves Runtime:** The retrieved manual exposes real controls for Host+2, grids, custom coordinates, gap, 5 px example borders, per-source PTZ, solo transitions, and automatic or manual highlighting. **My inference for Runtime:** do **not** use its audio-driven zoom; use only a border/tally state with about 300 ms attack and 600 ms release so coughs do not flash the frame. For the two-to-three transition, keep each 620×700 host aperture and its internal transform fixed: begin with the two apertures touching as a centred 1240×700 pair, then translate them outward while a 600×700 centre card grows from the covered seam. Nothing inside either host crop scales.

### Riverside split-screen podcast layouts
- **Source:** https://riverside.com/blog/how-to-make-an-split-screen-video
- **Steal:** Offer a gap/no-gap pair layout and a speaker-led layout as states of the same source set, with reframing stored per source.
- **Why it serves Runtime:** The retrieved product guide documents podcast interviews in side-by-side layouts, grids with or without gaps, speaker views with other participants on the side, and explicit crop/reframe controls. Runtime's source geometry makes an unusually honest version possible: each generated half is 672×768 (0.875:1), almost the same shape as a 620×700 host well (0.886:1). **My inference:** in paired-host mode, place the two wells edge-to-edge and align their crop origins so the desk line and background continue across a single 1 px seam; in three-box mode, move the same wells apart and let the centre card cover that seam. The audience can read the pair as one wide shot intentionally windowed in two, not as two falsely independent cameras.

### Gemini dual-market panel
- **Source:** https://mobbin.com/screens/6d00b119-4569-46a0-9249-150f4cf14cc6
- **Steal:** Use two equal, self-contained dark panels with one shared baseline and a narrow, plain divider rather than decorative frames.
- **Why it serves Runtime:** I inspected the retrieved screen: two near-identical rounded market panels sit side by side, each repeating the same header, table, controls, and footer hierarchy. **My inference:** this is the right structural reference for the paired-host state—equal apertures, repeated name/state furniture, shared alignment—but Runtime should use squarer corners and an 8 px border because the screen's fine grey strokes would disappear at 480p.

### Braintrust monitor grid, with Binance density boundary
- **Source:** https://mobbin.com/screens/f656d443-cfa5-413d-a20f-ccfac296bf58 and https://mobbin.com/screens/f52a4ec7-7ef6-49a0-a70a-ec6b308af97e
- **Steal:** Borrow the monitor grid's repeated card dimensions and stable gutters, while borrowing from the trading screen only its strong modal-over-background hierarchy.
- **Why it serves Runtime:** I inspected both retrieved screens. Braintrust uses a regular three-column card grid with consistent gaps and identical chart anatomy; Binance places a compact date modal above a dimmed, extremely dense trading surface. **My inference:** Runtime should reuse one centre-card shell for guest/chart/image/tweet content and dim the host wells by roughly 15–20% only for text-heavy cards. Do not copy Binance's information density; the useful concept is that the centre layer can become unequivocally primary without changing the underlying layout.

## Avoid

- **Four equal live panes.** Twitch reported that viewers found Squad Stream's four-up view of multiple gameplay angles overwhelming, and the product was retired: https://blog.twitch.tv/en/2023/12/13/retiring-squad-stream. Two hosts plus one content target already create three attention demands; a fourth persistent box would erase hierarchy.
- **Audio-driven resizing or constant solo cuts.** mimoLive supports automatic highlighting by making the active speaker more prominent, but Runtime's two crops share one generated wide source. Resizing one half exposes mismatched resolution and makes character drift more obvious. Keep geometry still; change only a thick border and attached state tab.
- **Thin neon/glowing outlines.** They look tempting in esports packages but are exactly the kind of fine, low-contrast edge Twitch encoding damages. Use a flat 8 px keyline at 1080p, with one saturated state colour and no bloom.
- **A new outer layout for every centre payload.** A guest, chart, static image, and tweet should all enter the same centre well with `cover` only for guest video and `contain` for information. Redesigning the frame per payload will look assembled and create more failure points than a modular card system.
- **Generating “two angles” and presenting them as separate cameras.** A retrieved Midjourney exploration recommends prompting a split screen with a close-up on one side and a full body on the other: https://hendrikvanzwol.substack.com/p/midjourney-en-ik-zijn-weer-samen. Strict spatial separation is a useful composition phrase, but the differing viewpoints are wrong here: Runtime has one wide two-shot. Preserve shared desk height, eyeline, lighting, and background continuity so the crop relationship remains truthful.

## What I could not answer

- I did not find a publicly documented live show that deliberately advertises two separated side panes as crops of one continuous wide camera. The recommendation above is therefore **my inference from Runtime's exact source and aperture ratios**, not an observed broadcast convention.
- Public X search returned no directly retrievable X post pages for the requested multibox terms. I inspected an ESPN PR post only through the retrieved BlimpCast article that embeds and quotes it; I am not citing a guessed `x.com` status URL.
- I found no useful, inspectable Midjourney multibox **broadcast** exploration. The retrieved split-screen character experiment is included only as a clearly marked avoid; it does not justify generating Runtime's deterministic OBS layout.
- StreamYard's retrieved documentation describes reusable camera grids, camera slots, one media slot, and custom layouts, but its page did not provide enough stable visual evidence in this environment to make it a top visual pick. Likewise, several CNBC portfolio pages timed out or returned 404 on direct fetch, so the CNBC recommendation relies on the successfully retrieved Brainstorm case-study PDF.
