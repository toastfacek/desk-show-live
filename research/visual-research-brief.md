# Runtime — Visual Research Brief

A brief for a parallel multi-agent search task. Six independent lanes, one agent each. Nothing here needs the repo — every lane is self-contained.

**What this is for:** M0 is blocked on art. `studio.yaml` describes the hosts and set in words, but those words were written cold. This gathers real reference so the descriptions can be sharpened before we spend anything baking a hero still.

---

## How to run it

1. Spawn six agents, one per lane (§3). Give each **the shared preamble (§2) verbatim, followed by its lane only.**
2. Each writes its findings to `research/findings/L<n>-<slug>.md`.
3. Lanes are independent — no agent needs another's output. Run them all at once.
4. When they land, a merge pass reconciles them into a revised `studio.yaml` and a graphics spec.

Lanes 1, 2 and 6 feed the **generated** layer (what fal draws). Lanes 3, 4 and 5 feed the **deterministic** layer (what OBS draws). Those two never mix — see the constraints.

---

## 2. Shared preamble

> Copy this into every lane agent, above its lane brief.

You are researching visual reference for **Runtime**, a live desk show streamed to Twitch. Two original cartoon robot hosts sit at a desk and react to a feed of tech and VC posts. The hosts are called PHASEONE[lol] and deb.

**How the show is actually made — this constrains everything you recommend:**

- A video model generates exactly one thing: a **wide two-shot of both hosts at a desk**, 5 seconds at a time, 1344×768.
- OBS crops that single clip **50/50** — left half and right half — and places each half in its own box on a 1920×1080 canvas, roughly 620×700 each. A card sits on top of the middle, covering the seam.
- Everything else on screen is drawn by OBS at true 1080: chyron, lower thirds, tickers, sponsor bar, clock, LIVE badge, the centre card.
- Each 5-second clip is chained off the last frame of the previous one, so the characters **drift** slowly take to take.
- The stream goes out through Twitch's encoder at a normal bitrate.

**Hard constraints. A recommendation that violates one of these is useless to us.**

1. **No IP cloning.** You may and should identify named works, studios and shows as reference — that is what research is for, and a human will look at them. But every recommendation must also be expressed as an **original descriptive sentence** that never names the source. We cannot put "in the style of <show>" into a generation prompt: it invites a safety-checker rejection and it is exactly what got a similar project banned from Twitch. Describe the *technique*, not the trademark.
2. **Drift tolerance is a design requirement.** The characters will subtly change shape between clips. Designs with few facial degrees of freedom — strong silhouette, simple geometry, occluded or stylised mouths — hide this. Photoreal or detail-dependent designs expose it. Weight your recommendations accordingly.
3. **Legibility at 620×700, and at 480p.** A character or graphic that only works full-frame is no use. We may generate at 480p to cut cost by 38%, which means a half-frame crop of an 854×480 image gets upscaled ~1.45×. Fine detail, thin lines and subtle gradients will not survive.
4. **Twitch encoding eats thin lines, fine dither and low-contrast gradients.** This applies hardest to the graphics lanes.
5. **No readable text inside the generated frame, ever.** Video models garble text and re-garble it every clip, so it flickers. Any typography you recommend is for the OBS layer only. Never recommend set dressing with legible words, signage or logos in it.

**Output contract. Write your findings to `research/findings/L<n>-<slug>.md` in exactly this shape:**

```markdown
# L<n> — <lane name>

## Top picks
For each, 4–8 of them:

### <name of the work / studio / show / system>
- **Source:** <URL — must be a real URL you actually retrieved, never one you assembled from memory>
- **Steal:** <one sentence: the specific technique to take>
- **Why it serves Runtime:** <which constraint above it satisfies, named>
- **Prompt-safe wording:** <one to three sentences describing the technique in original language, naming nothing. Omit for lanes 3, 4 and 5.>

## Avoid
Three to five things that look tempting and are wrong for us, each with the reason.

## What I could not answer
Anything the lane asked for that you could not find. Say so plainly rather than filling the gap.
```

**Two rules on sourcing.** Every URL must come from a search result you actually retrieved — never reconstruct a plausible-looking link from memory. Prefer image-dense sources a human can scan quickly. If a claim is your own inference rather than something a source states, mark it as yours.

---

## 3. The lanes

### L1 — Character design: expressive robots with almost no face

**Question:** What are the design techniques that let a flat 2D cartoon robot read as a specific, expressive character when it has two eyes, no real mouth, and is being redrawn slightly differently every five seconds?

Find and analyse:
- 2D animation traditions built on heavy uniform linework and flat colour fields — how they get expression out of very few moving parts
- Robot and mascot character design where **silhouette alone** carries identity
- How designers substitute for a mouth: LED strips, waveform displays, visor bands, hinged jaw plates, single-shape mouths, or no mouth at all with all expression pushed into eyes and brows
- Eye design as the primary emotional channel — brow plates, pupil shape, lens geometry, how much a two-dot face can convey
- **Two-character contrast:** how a designer makes two characters in the same frame instantly distinguishable by silhouette and colour alone, so that a viewer squinting still knows who is who
- Character sheets and turnarounds that are built to be reproduced consistently by many hands — the closest existing analogue to our drift problem

Also useful: anything written about designing for **low frame counts or limited animation**, since our clips have no motion blur and hold a lot.

Deliverable emphasis: the prompt-safe wording matters most in this lane. It goes straight into `studio.yaml`.

---

### L2 — The set: a TV studio built inside a startup office

**Question:** What does a retro-futurist broadcast set look like when it is really a converted tech office, and how is it lit so that two characters read cleanly against it?

Find and analyse:
- Real small-studio and podcast-studio set design — desk shapes, depth, what goes behind the hosts
- **CRT and monitor walls** as set dressing: stacking, mixed housings, cable management as texture, what they display when they are not displaying anything
- Retro-futurist and analogue-futurist production design — chrome, moulded plastic, neon tubing, warm practical lamps
- **Asymmetric lighting** where one side is warm and the other cool, with a motivated in-world source for each. This is load-bearing for us: the two halves of the frame must stay distinguishable even in a badly rendered take.
- How sets keep the centre of frame visually quiet so graphics can sit over it
- Depth and fall-off: how backgrounds get dark or soft enough that foreground characters stay readable at small size

Avoid recommending anything with legible signage, logos or text — see constraint 5.

---

### L3 — The broadcast graphics package

**Question:** What is the actual anatomy of a modern broadcast graphics system, and what is the minimum set of elements that makes a stream read as a real production rather than a webcam?

This is the highest-leverage lane. It costs nothing to build and it is most of what sells the show.

Find and analyse:
- **Lower thirds and name bars** — construction, hierarchy between name and handle, animation in and out
- **Chyrons / headline bars** — how a headline and a kicker share one bar, how long they stay up, how they change
- **Tickers** — scroll speed, item separation, how sponsor tickers differ from market tickers, how two ticker rows coexist without noise
- **Bugs and furniture** — the corner logo, LIVE badges, clocks, "presented by" slots
- Financial and sports broadcast graphics specifically — the densest, most evolved versions of all of the above
- **Esports and streaming overlays** — the same problem solved for Twitch's encoder and a younger audience
- How a graphics package stays coherent: a shared grid, a shared corner radius, a shared skew angle, a consistent bar height

Pay attention to **safe areas** — how much of the bottom of frame the furniture eats, since that constrains where our host boxes can sit.

---

### L4 — Multibox layouts

**Question:** How do live shows compose two or three boxes plus a centre content slot, and what makes those layouts feel designed rather than assembled?

Find and analyse:
- Two-host and three-box layouts on live podcasts, finance streams and talk shows
- How a layout transitions between two boxes and three — what moves, what stays
- **Frames and borders** around boxes: weight, colour, whether they glow, and how a "who is speaking" indicator is expressed
- Where the centre slot's content sits relative to the host boxes — overlapping, inset, or in its own well
- Box aspect ratios and how hosts are framed within them
- How layouts handle a guest, a chart, a static image and a tweet in the same slot without redesigning
- Squad-stream and watch-party layouts, which solve the box-tiling problem hardest

Specifically useful to us: any layout where the two side boxes are clearly **crops of a single wider image**, and whether that reads as a cheat or as a style.

---

### L5 — Type and colour

**Question:** What typefaces and palettes does broadcast graphics actually use, what can we license, and what survives a Twitch encoder at small sizes?

Find and analyse:
- The typographic conventions of broadcast: condensed grotesques, extended faces for headlines, the numeral design that tickers depend on
- **Licensing.** For every typeface you recommend, state the licence and whether it permits use in a commercial stream. Open-licence alternatives to the standard broadcast faces are especially valuable — flag them explicitly.
- How type is set for legibility at ticker size against a moving background: weight, tracking, the case convention, whether a drop shadow or a solid plate is doing the work
- Palettes built around a **warm/cool split**, since our set is lit amber on one side and teal on the other
- Which colours survive video compression and which fall apart — saturated reds and fine gradients are the usual casualties
- Contrast ratios for text over a live video background

State clearly which recommendations are your inference and which come from a source that actually tests these things.

---

### L6 — Motion, transitions and idents

**Question:** What does the show's motion vocabulary look like — the cold open, the stings between segments, the transitions — given that all of it is baked once and replayed free forever?

Find and analyse:
- **Boot sequences and system-startup motifs** as title design: a show called Runtime should probably start by starting
- Broadcast idents and title sequences that establish a world in under five seconds
- Stinger transitions in streaming: how long they run, how the audio carries them, why they work
- Segment bumpers in talk and finance television — the shortest possible unit that says "we are changing subject"
- Wipes, glitch treatments and scanline effects that read as intentional rather than broken. This matters to us specifically: **our hosts will visibly drift and glitch**, so a motion language where instability is clearly a style choice makes the artefact look like a decision.
- How a music bed and a sting relate — what ducks, what carries

Everything here is a bake-once asset. Slow and expensive to make is fine; it plays free for the life of the show.

---

## 4. After the lanes land

The merge pass does four things:

1. Rewrites the `style`, `set` and two `sheet` blocks in `studio.yaml` using the prompt-safe wording from L1, L2 and L6.
2. Turns L3, L4 and L5 into a graphics spec — element inventory, grid, safe areas, type stack with licences, palette — which becomes the OBS scene collection at M0.
3. Reconciles conflicts. L2 and L4 will disagree about how much the background can do, because one wants a rich set and the other wants the boxes to dominate. That is a real tension and the merge resolves it rather than averaging it.
4. Re-runs the M0 approval gate criteria against the revised description **before** anything is generated, since a hero still costs money and every take in the show inherits it.
