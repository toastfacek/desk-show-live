# OBS scene contract (build by hand)

Code may switch these scenes and fill these inputs. Code may not create, delete, or rename them.

## Scenes

| Scene | Must contain |
| :---- | :---- |
| `wide` | `HOST_WIDE` full frame; `HEADLINE`; `NAME_A`; `NAME_B` |
| `split` | Two scene items of `HOST_WIDE` (left crop, right crop); `CENTER` on the join; `HEADLINE`; name bars |
| `solo_l` | Left crop of `HOST_WIDE`, larger |
| `solo_r` | Right crop of `HOST_WIDE`, larger |
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
