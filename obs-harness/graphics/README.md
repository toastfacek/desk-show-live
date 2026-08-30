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

## Preview vs Program

`preview.html` is a studio monitor. The dashed host wells and the warm/cool wash behind them are fake, so you can click layouts without OBS. They never go to Twitch.

`overlay.html` is what actually sits on Program: a transparent 1080 Browser source named `FRAME`. Chyron, tickers, LIVE, names, frames, and the card are this file.

The hosts on stream are not HTML. They are the OBS media source `HOST_WIDE` (a clip from `assets/clips/` today; fal later). OBS crops that file into the left and right boxes. This pack only draws the chrome around them.

**What to edit for each layer**

| What you want to change | Where |
| :---- | :---- |
| Look of the chrome (type, colour, bar height) | `overlay.css` / `overlay.html` |
| Headline, which card, layout plan | `rundown.yaml` |
| Post text on the card | `posts.json` |
| Host names | `overlay.py` (`DEFAULT_HOSTS`) — display only, never in a video prompt |
| Lines the hosts say | `script.jsonl` |
| Pictures in the host boxes | `assets/clips/*.mp4`, pointed at `HOST_WIDE` in OBS |
| Room / characters | Generated video + `studio.yaml`. Not this HTML. |

The harness writes `out/overlay_state.json` on every cut. The overlay polls it. That is how a fake run or a later OBS run drives the furniture without you clicking preview buttons.

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

- Canvas 1920×1080. Side pad 32, no gutter. Stage 792 tall under the header.
- Split is three equal columns, flush: host · card · host.
- `solo_l` is host left + info window right. `solo_r` is the mirror.
- Host names: `PHASEONE[lol]` never lowercases; `deb` never capitalizes.
