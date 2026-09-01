"""Capture the official tweet still and cover-crop it for overlay wells."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from runtime_flight.tweet_embed import embed_frame_path
from runtime_flight.tweet_shot import (
    TweetShotError,
    capture_embed_shot,
    crop_program_well,
    write_shot_set,
)


def _from_obs(dest: Path) -> Path:
    import base64
    from io import BytesIO

    from PIL import Image
    from obsws_python import ReqClient

    password = os.environ.get("OBS_WEBSOCKET_PASSWORD")
    if not password:
        env = Path.home() / ".config/desk-show/obs.env"
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("OBS_WEBSOCKET_PASSWORD="):
                password = line.split("=", 1)[1].strip().strip('"')
                break
    if not password:
        raise TweetShotError("missing OBS_WEBSOCKET_PASSWORD")
    client = ReqClient(host="127.0.0.1", port=4455, password=password, timeout=8)
    shot = client.get_source_screenshot("split", "png", 1920, 1080, 100)
    data = shot.image_data
    if data.startswith("data:"):
        data = data.split(",", 1)[1]
    program = Image.open(BytesIO(base64.b64decode(data)))
    write_shot_set(crop_program_well(program), dest)
    return dest / "tweet-shot.png"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, default=Path("/tmp/runtime-design-preview"))
    parser.add_argument("--tweet-id", default="2094640985116737882")
    parser.add_argument("--embed-origin", default="http://127.0.0.1:8766")
    parser.add_argument("--from-obs", action="store_true")
    args = parser.parse_args()
    try:
        if args.from_obs:
            path = _from_obs(args.dest)
        else:
            try:
                path = capture_embed_shot(
                    args.embed_origin.rstrip("/") + embed_frame_path(args.tweet_id),
                    args.dest,
                )
            except TweetShotError:
                path = _from_obs(args.dest)
    except TweetShotError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
