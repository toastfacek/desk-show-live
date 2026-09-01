# OBS + streaming setup (the monetizable path)

The MVP loop deliberately contains **zero streaming code** — OBS carries the stream.
That keeps the live path identical whether you're testing in a window or broadcasting.

## Scene setup (10 minutes)

1. Run the show: `python3 run_live.py` (player `mpv`). The mpv window is the host feed —
   full-frame 1344×768 talking head, freeze-frame holds included.
2. In OBS create a scene:
   - **Background**: Image source — your static set JPEG/PNG (desk, studio, monitor
     frame). Any 1920×1080 image.
   - **Host feed**: *Window Capture* of the mpv window. Scale/crop it into the
     "monitor" region of the set for the desk-show PiP look. (macOS: grant OBS screen
     recording permission; Linux: use PipeWire/xcomposite window capture.)
   - Optional plate: show `assets/hero.png` behind/instead of the feed before the show
     starts.
3. Alternative without mpv (`player: folder` in config): add a **VLC Video Source**
   pointed at `out/ready/` with "loop playlist" off and playlist re-scan on — clips play
   as they land. mpv + window capture is smoother (mpv owns the gapless/hold logic);
   folder mode is the fallback.

Audio: capture mpv's audio (desktop audio capture, or an audio loopback device if you
want it isolated). The robot voice chain is already baked into the ready files.

## Going live

OBS → Settings → Stream → pick the service (Twitch / YouTube / Kick), paste the stream
key, Start Streaming. 1344×768 canvas output at 24fps matches the clips; upscale the
canvas to 1080p if the platform prefers it.

## Monetization reality check (from the spec's cost table)

| | generation cost/hr (768p) |
| :-- | :-- |
| promo (ends 1 Sep 2026) | ~$144, ~$220–290 with retry multiplier |
| list | ~$288, ~$430–580 with retry multiplier |

So 24/7 streaming is a ~$10k/day habit at list rates. Shapes that can actually pay:

1. **Scheduled short live blocks** (30–60 min daily) on Twitch/YouTube — subs, bits/
   superchats, sponsor reads written straight into the writer's topic seeds. Cost per
   block is bounded and known from E7's real $/min.
2. **Clips-first**: run short generation sessions, publish the best takes as
   Shorts/TikToks, go live only for events. Generation cost scales with output you keep.
3. **Paid/private shows**: sponsored segments or member-only streams where the topic
   seeds are the product.

Decide after E7 — the manifest gives the real $/min including retries, which is the
number every one of these plans divides by. Platform note from the spec: original
characters only; the DMCA ban that inspired this project is the cautionary tale.
