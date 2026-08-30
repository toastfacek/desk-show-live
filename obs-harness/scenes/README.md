# OBS scene contract (build by hand)

Code may switch these scenes and fill these inputs. Code may not create, delete, or rename them.

Furniture (chyron, tickers, LIVE, clock, card, host frames) is HTML in `../graphics/`. Add one Browser source named `FRAME`, 1920×1080, transparent, on every scene, above `HOST_WIDE`. See `../graphics/README.md`.

## Scenes

| Scene | Must contain |
| :---- | :---- |
| `wide` | `HOST_WIDE` full frame; `HEADLINE`; `NAME_A`; `NAME_B` |
| `split` | Two scene items of `HOST_WIDE` (left crop, right crop) in the left and right columns; card in the middle column; `HEADLINE`; name bars |
| `solo_l` | Left crop of `HOST_WIDE` filling the left; info window (card) on the right |
| `solo_r` | Right crop of `HOST_WIDE` filling the right; info window (card) on the left |
| `card_full` | `CENTER` full frame. `HOST_WIDE` may be hidden; its audio stays in the mixer |
| `hold` | `CENTER` or a still; `BED` audible. No host face as the only picture |

## Inputs

| Name | Kind |
| :---- | :---- |
| `HOST_WIDE` | Media source — the only file `play_clip` changes |
| `CENTER` | Browser or image |
| `HEADLINE` | Text |
| `NAME_A` `NAME_B` | Text |
| `HL_A` `HL_B` | Color or border (speaking highlight) |
| `BED` | Audio |

## Crop-sync check (H0)

1. Point `HOST_WIDE` at `assets/clips/sync_check.mp4`.
2. Switch to `split`.
3. Play.
4. Pass: both halves hit the cut at 2.5s together. Fail: they drift. **Stop. Do not add layouts.**
