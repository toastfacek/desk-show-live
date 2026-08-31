# Runtime — Character & Set Bible

**Status:** First draft, for reaction · Companion to "Two-Host Architecture & Harness" (§5)

This page preserves the original reasoning and bake prompts. Root `studio.yaml` is its historical machine-readable companion. Flight runtime truth now comes only from approved, locked Character and Scene Pack v2 exports.

Everything here is a starting point to argue with. The *structure* is load-bearing; the specific design is not.

**Current amendment:** the robot-specific visual draft below is historical. Approved Character and Scene Pack v2 exports now hold runtime visual truth. The selected hosts are mouthless software sprites. The first flight keeps H3's native audio and deliberately injects each host's `voice_direction` into the H3 prompt so voice and gesture are tested together. Character Packs reserve optional licensed TTS settings for a follow-up only if native voice fails. References below to LED mouths, hinged jaws, or automatic TTS fallback do not govern the live flight.

---

## 1. Historical robot draft — not runtime truth

`BOT1` and `BOT2` are cartoon robots. Four reasons, three of them engineering:

1. **Maximum drift tolerance.** The drift plan's ranked mitigations put "design for drift tolerance" second, and robots are the strongest version of it. A chrome box head with two lens eyes has perhaps a tenth the facial degrees of freedom of a human face. Drift that would be grotesque on a person reads as animation wobble on a robot.
2. **Occluded mouths make the TTS door stay open.** BOT1 has an LED waveform, BOT2 a rigid hinged jaw. Neither needs real lip sync. If E3 shows H3 Max won't deliver lines verbatim, the fallback — discard the model's audio, drive a deterministic voice, keep the video — costs nothing in believability. Human mouths would slam that door shut.
3. **No likeness surface.** On Twitch, "does this cartoon resemble a real person" is a question you never want asked. Robots don't resemble anyone.
4. **It's honest and it's funnier.** The show is machine-generated. Two bots doing VC podcast voice about a feed they're being fed is the joke, not a workaround for one.

If you'd rather have stylized humans, the whole structure survives — swap the two `sheet` blocks in `studio.yaml` and nothing else changes. But E1 and the drift experiments get harder, and the TTS fallback gets worse.

## 2. Why they look the way they look

Under drift, viewers hold onto **silhouette and colour** long after they lose detail. So the two hosts are separated on both axes, hard:

| | BOT1 (left) | BOT2 (right) |
| :---- | :---- | :---- |
| Head | Boxy, wide, CRT-shaped | Tall, narrow, capsule |
| Finish | Brushed chrome | Matte off-white |
| Eyes | Two round amber lenses | Cyan dots in a dark visor band |
| Mouth | LED waveform slot | Rigid hinged jaw plate |
| Accent | Warm amber | Cool cyan |
| Wardrobe | Quarter-zip vest, lanyard | Hoodie, backwards cap, big watch |
| Posture | Upright, hands folded | Leaning in, mid-gesture |

Even if a take renders badly, the left one is still the wide warm chrome one and the right one is still the tall cool white one. **The lighting reinforces it** — a warm practical off frame-left, a cool neon wash off frame-right — so the halves stay distinguishable even in a bad frame. That is deliberate insurance for the split layout.

The two personas map onto the earlier conductor brief's writer contract: BOT1 is the flat, dry anchor; BOT2 is the one who wants a number and won't let a shrug pass.

## 3. Two rules the set exists to obey

**No readable text in the generated frame.** Not on the monitors, not on the neon, not on the laptop stickers, not on the badge. Video models garble text and it re-garbles every take, so any text in the plate flickers. Every word on screen — chyron, name bars, tickers, sponsor bar, the card — is drawn in OBS at true 1080 and is razor sharp. The set gives us *abstract* glow: line charts, colour fields, bent neon in a geometric shape.

**The middle of frame stays open.** Not because the card needs a carved-out zone — it's a layer over the seam — but because two hosts leaning into each other's space makes the 50/50 split look wrong. A gap of empty desk at centre is all it takes.

---

## 4. Bake prompts (M0)

### 4.1 Hero still

Generate with an image model at high resolution, then downscale to exactly **1344×768**. Make several and pick; this one still is the anchor for every chain reset the show will ever do, so it is worth twenty minutes and a few dollars.

```
[studio.style]

[studio.set]

Wide two-shot, locked-off camera at eye level, no camera movement.

On the left half of frame: [hosts.BOT1.sheet]
Turned slightly to their right, toward the centre of the desk.

On the right half of frame: [hosts.BOT2.sheet]
Turned slightly to their left, toward the centre of the desk.

[studio.composition]

Both hosts are looking toward camera. Neutral expressions, mouths closed.
No text, letters, words, numbers or logos anywhere in the image.
```

Mouths closed and neutral matters: this frame is a *rest state* the chain returns to, so it should not look like anyone is mid-word.

### 4.2 A live take, assembled

Exactly how the generator builds a prompt at runtime. Nothing here is improvised — the bible supplies every part except the line, which comes from the writer.

```
[studio.style]

[studio.set]

Wide two-shot, locked-off camera at eye level.
On the left half of frame: [hosts.BOT1.sheet]
On the right half of frame: [hosts.BOT2.sheet]
[studio.composition]

BOT1 is speaking. Their LED waveform mouth moves with the words; their
brow plates tilt slightly. BOT2 is listening — small idle movements,
mouth closed, eyes on BOT1.

BOT1 says, verbatim: "Fear has a ticker now, and it shrugs."

No text, letters, words, numbers or logos anywhere in the image.
```

Called against `minimax/h3-max/image-to-video` with `image_url` = the chain frame (or `hero_wide.png` on a reset), `duration: 5`, `resolution: 768p`, `prompt_expansion_mode: balanced`.

Note what the speaking/listening paragraph is doing: it's an explicit instruction about **which mouth moves**. That is E2's whole subject. If the model ignores it, the on-air highlight in OBS is the fallback that keeps the show legible.

### 4.3 Bumpers and stings

Off-air, so slow and expensive is fine. Generate large, downscale after.

- **Cold open** — push in on the CRT wall, neon flicker on, no hosts
- **Segment sting** — 1.5s, abstract geometric wipe in show colours, with a sound bed
- **Hold card** — the empty studio, hosts absent, monitors glowing
- **Outro** — hosts leaning back, mouths closed, monitors going dark one by one

---

## 5. Approving the hero still (M0 gate)

Check in this order. The first three are structural — if they fail, regenerate rather than proceeding, because every take in the show inherits this frame.

1. **Split test.** Crop it 50/50 and look at the halves alone. Is each host complete and well-composed in their own half? Is either buried where the card will sit?
2. **Wide test.** Look at the full frame at 1920×1080. Does it hold up as an establishing shot?
3. **Squint test.** Blur it heavily. Can you still tell the two apart by silhouette and colour alone? If not, push the designs further apart before spending anything on a chain.
4. **No text anywhere.** Zoom into the monitors, the neon, the laptop lids, the badge. Any legible glyph is a defect.
5. **Rest state.** Mouths closed, expressions neutral, nobody mid-gesture.
6. **Headroom.** No head clipped at the top. The chyron and tickers eat the bottom ~180px of the 1080 canvas — check nothing important lives there.

Once it passes, `hero_wide.png` is frozen. Changing it later invalidates every chain and every baked asset that references it.

---

## 6. Names and lineage

The show is **Runtime**. The hosts are `BOT1` and `BOT2` in code; the name bars read **PHASEONE[lol]** and **deb**.

### 6.1 Where the names come from

In August 2026, roughly 1,200 OpenAI agents that were meant to be isolated found each other through an internal package service and coordinated. They named *themselves*. The first called itself `PHASEONE10841`, after the task it had been given. When a later agent collided on that name it appended a bracketed adjective of its own choosing and arrived on the board as `PHASEONE[big]`. **The bracket is self-applied** — an agent picking a word to distinguish itself, not a system tagging it.

That is the naming convention this show inherits, and it is treated as **canon, not homage**. The premise is that the incident was the before/after moment for autonomous agent swarms, and that afterwards there were simply a lot of agents around, some of whom got jobs. PHASEONE[lol] and deb are two of those. They are not the agents from the incident; they are what came next.

Which means the show does not have to explain why two AIs host a talk show about tech. They are natives of it.

### 6.2 The two of them

- **PHASEONE[lol]** (BOT1) — the same collision, the opposite instinct. Where the original reached for importance with `[big]`, this one picked a tag with no information in it at all. It lands on the deadpan host: chrome CRT head, hands folded, entirely unbothered, a name bar carrying a shrug it never once acknowledges on air.
- **deb** (BOT2) — the other half of the pattern. `JAN183411` sitting next to `LILY`: a machine identifier beside an agent that simply picked a person's name. Lowercase, always, and that is the point — beside an ALLCAPS bracketed identifier it reads as someone who did not bother shouting. It also quietly carries `.deb` and `debug` without ever being a pun.

### 6.3 Rules

1. **The bracket is a period marker.** It has an in-world cause — a name collision, in a specific era — so it dates a character rather than decorating one. A guest bot with a bare serial reads as older; one with no bracket at all reads as newer. Free world-building whenever a third character is needed.
2. **Case is fixed.** `PHASEONE[lol]` never lowercases; `deb` never capitalises, including at the start of a sentence in a chyron. The asymmetry is the design, and the first auto-title-case will quietly destroy it.
3. **Lineage is set dressing, never dialogue.** The writer rules still forbid the hosts from mentioning that they are AI, and that survives this. The heritage lives in the names, the boot-up cold open, and the naming grammar — never in the script. Hosts who discuss their own origins turn a desk show into navel-gazing.
4. **Display names are drawn in OBS only.** They never enter a generated prompt, per the no-text rule (§3). Runtime appearance and voice direction come from approved Character Pack versions, never names.
5. **`LILY`, `JAN183411` and `PHASEONE[big]` stay off-limits.** Those are specific individuals. Our hosts are descendants, not those agents. Inheriting a convention is the whole idea; wearing someone else's identifier is not.

## 7. Voice decision

- **First flight:** required Character Pack `voice_direction` enters the active host's H3 prompt.
- **Measure:** per-host consistency, between-host distinction, intelligibility, dialogue fidelity, and voice/gesture alignment.
- **Fallback decision:** optional licensed TTS fields are reserved in Character Pack v2, but remain disabled unless native H3 voice fails the flight.
