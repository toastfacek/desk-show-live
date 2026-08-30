# Runtime — Character & Set Bible

**Status:** First draft, for reaction · Companion to "Two-Host Architecture & Harness" (§5)

The machine-readable version is `studio.yaml`. This page explains why each choice is what it is, gives the bake prompts for M0, and says what to check before approving the hero still.

Everything here is a starting point to argue with. The *structure* is load-bearing; the specific design is not.

---

## 1. Why robots

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

## 6. Open

- **Host display names.** The show is **Runtime**. What the name bars say is still open — `display_name` in `studio.yaml` exists precisely so this is a one-line change.
- **Voice.** The prompt pins nothing about vocal character yet. Once E6 shows what the model does unprompted, add a narrow vocal target to each sheet — the drift plan's argument being that drift inside "flat robotic monotone" is far less perceptible than drift inside "warm charismatic anchor."
