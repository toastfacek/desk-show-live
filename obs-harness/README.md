# OBS Harness

A clock that sits next to stock [OBS Studio](https://obsproject.com/) and runs a show from files. It does not fork OBS. It does not call a language model. It does not buy video.

## Make it real

On the machine that has OBS:

1. OBS 28+. **Tools → WebSocket Server Settings** — enable, note the port (4455).
2. `export OBS_WEBSOCKET_PASSWORD=...` if you set one.
3. `pip install 'obsws-python>=1.7' pyyaml`
4. Build the six scenes once:

```bash
cd obs-harness
python3 scenes/install.py
```

5. Run the show. This starts the overlay server, talks to Program, and uses **wall time**:

```bash
python3 run.py --player obs
```

Watch OBS Program. `FRAME` is `graphics/overlay.html`. `HOST_WIDE` is the clip. The harness switches `wide` / `split` / `solo_l` / `solo_r` / `card_full` / `hold` and writes `out/overlay_state.json` so the chrome follows the cut.

If a named scene is missing, the process exits 4. It does not invent a scene.

## Tests (no OBS)

```bash
python3 -m pytest -q
python3 run.py --player fake
```

`--mode live` exits 2. Text + fal are a different package.

## What is on Program

| Layer | Source |
| :---- | :---- |
| Hosts | OBS input `HOST_WIDE` — files from `assets/clips/` |
| Chrome | Browser source `FRAME` — `graphics/overlay.html` |
| Copy | `rundown.yaml`, `posts.json`, `script.jsonl` |

`preview.html` is only a monitor. It is not the stream.

## License

Intended MIT when this tree is its own repo.
