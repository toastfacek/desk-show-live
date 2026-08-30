# OBS Harness

A clock that sits next to [OBS Studio](https://obsproject.com/) and runs a show from files.

This package does **not** call a language model and does **not** buy video. Clips come from `assets/clips/`. A later package can plug in your text API and fal.

## Run the demo (no OBS)

```bash
cd obs-harness
python3 -m pytest -q
python3 run.py --player fake
```

Writes `out/takes.jsonl` and `out/overlay_state.json`.

## Preview the frame (no OBS)

```bash
cd obs-harness
python3 -m http.server 8765
```

Open http://127.0.0.1:8765/graphics/preview.html  
That is the chyron, tickers, name bars, and host frames. Click the six layouts. The video wells are placeholders — real `HOST_WIDE` lives in OBS.

## Talk to OBS

1. Install OBS 28+. Enable **Tools → WebSocket Server Settings**.
2. Build the scenes and inputs listed in `scenes/README.md`.
3. Prove crop-sync (same README). If the split drifts, stop.
4. `export OBS_WEBSOCKET_PASSWORD=...`
5. `python3 run.py --player obs` checks the connection. The 90s desk run is the H4 gate in `OBS Harness — TDD.md`.

## License

Intended MIT when this tree is its own repo.
