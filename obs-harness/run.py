#!/usr/bin/env python3
"""Run a rehearse show. Fake player by default. OBS when --player obs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from loop import Harness
from player_fake import FakePlayer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OBS harness — rehearse only")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--rundown", default=None)
    parser.add_argument("--player", choices=("fake", "obs"), default=None)
    parser.add_argument("--mode", default=None)
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = yaml.safe_load(config_path.read_text()) if config_path.exists() else {}

    mode = args.mode or config.get("mode") or "rehearse"
    if mode != "rehearse":
        print("this package only runs rehearse. live sockets are a different package.", file=sys.stderr)
        return 2

    player_name = args.player or config.get("player") or "fake"
    rundown = Path(args.rundown or config.get("rundown") or root / "rundown.yaml")
    if not rundown.is_absolute():
        rundown = root / rundown

    stub = config.get("stub") or {}
    if player_name == "obs":
        from player_obs import ObsPlayer

        obs_cfg = config.get("obs") or {}
        player = ObsPlayer(
            host=obs_cfg.get("host", "127.0.0.1"),
            port=int(obs_cfg.get("port", 4455)),
        )
        try:
            player.connect()
        except Exception as exc:
            print(f"OBS not connected: {exc}", file=sys.stderr)
            return 2
        print("OBS connected. Simulated clock still drives this first cut; use fake for tests.")
        # Realtime OBS drive is H3/H4 on a desk. Keep the same loop with FakePlayer
        # timebase and fan calls out — not wired yet beyond connect check.
        _ = player

    harness = Harness.from_rundown(
        rundown,
        stub=stub,
        clip_duration_s=float(config.get("clip_duration_s") or 5),
        player=FakePlayer(),
    )
    harness.run_simulated(max_t=float((yaml.safe_load(rundown.read_text()) or {}).get("show", {}).get("target_len_s") or 90))
    log_path = harness.write_log()
    print(f"wrote {log_path} ({len(harness.log)} rows, {len(harness.beats)} beats)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
