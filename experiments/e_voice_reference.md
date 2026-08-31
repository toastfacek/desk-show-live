# Test path — pin two host voices via reference audio

**Not the live path.** Live flights stay on `minimax/h3-max/image-to-video` (prompt + first/last frame only). Do not point `video.endpoint` here.

**Endpoint:** `minimax/h3-max/reference-to-video`

**Why:** H3 Max image-to-video has no `voice_id`. This sibling endpoint accepts `reference_audio_urls` (2–15s each, combined ≤15s, must also send at least one image or video). Official MiniMax H3 can do the same, slower and on a different bill.

## Setup (off-air)

1. Bake one original 5s line per host that already sounds like the locked `voice_direction` (PHASEONE[lol] low/dry, deb high/clipped). Do not use a real person's voice or a soundalike.
2. Keep those WAVs with the locked hero still. They are the voice pins.
3. Call reference-to-video with:
   - `reference_image_urls`: locked Light Media Club hero
   - `reference_audio_urls`: that host's pin
   - prompt cites `Image 1` / `Audio 1` and includes the spoken line plus that host's `voice_direction`

## Gate

Eight alternating takes (BOT1 / BOT2). Blind listen:

- each host is recognizable to its own pin
- the two voices stay distinguishable
- picture still matches the locked still

Ten takes is about $2 at 768p list. Fail → do not adopt. E6 still opens TTS-first if native voice (prompt-only or this pin) cannot hold.

## Out of scope

- Switching the live flight endpoint
- Mixing this audio with TTS on the same show
- Cloning anyone
