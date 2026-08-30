# Runtime graphics pack

HTML furniture for a 1920×1080 OBS canvas. The video model never draws this.

IBM Plex (Sans, Sans Condensed, Mono) is SIL Open Font License. Files are vendored in `fonts/`.

## What it is

| File | Role |
| :---- | :---- |
| `overlay.html` | Transparent 1080 frame. Drop this on Program as a Browser source. |
| `preview.html` | Same overlay over placeholder host wells. Six layout buttons. |
| `state.example.json` | Shape the harness writes to `out/overlay_state.json`. |

The overlay always draws: LIVE, wordmark, clock, chyron, two tickers, name bars, host frames, center card. Layout (`wide` / `split` / `solo_l` / `solo_r` / `card_full` / `hold`) only shows or hides boxes. Tickers keep moving on hold.

## Preview (no OBS)

```bash
cd obs-harness
python3 -m http.server 8765
```

Open http://127.0.0.1:8765/graphics/preview.html

In another terminal, `python3 run.py --player fake`. The overlay polls `out/overlay_state.json` every 250 ms.

## OBS

1. Browser source, 1920×1080, **transparent**.
2. URL: `http://127.0.0.1:8765/graphics/overlay.html` (same server as above).
3. Name it `FRAME`. Put it on every scene, full canvas, above `HOST_WIDE`.
4. Do **not** turn on “Shutdown source when not visible” — tickers should keep running.
5. Crop-sync still happens on `HOST_WIDE` in `split`. This file does not touch that.

Headline and names live here so the first drop-in looks like a show. H3 can still drive OBS Text inputs `HEADLINE` / `NAME_*` if you hide the HTML twins. Do not let both show the same string.

`set_ticker` is still deferred. Sponsor and tape rows are baked into the state file for now.

## Grid

- Canvas 1920×1080. Side pad 40. Bottom furniture 180 (chyron 84 + two ticker rows).
- Split host boxes 620×700. Card 640×540 on the join.
- Host names: `PHASEONE[lol]` never lowercases; `deb` never capitalizes.
