"""Apply Runtime template-one wells after setup-obs. Decode once, crop twice."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from obsws_python import ReqClient

from runtime_flight.obs_setup import (
    DEFAULT_WATCHDOG_URL,
    setup_obs,
    validate_contract,
)

ALIGN_TOP_LEFT = 5
SOURCE_W = 1344
SOURCE_H = 768
HALF_W = SOURCE_W // 2
CANVAS_W = 1920
CANVAS_H = 1080
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLIP = REPO_ROOT / "assets" / "clips" / "sync_check.mp4"
DEFAULT_RECORD_DIR = REPO_ROOT / "out" / "obs-recordings"
HIGHLIGHT_COLORS = {
    "HL_A": 0xFFF2A541,  # BOT1 amber
    "HL_B": 0xFF2FB7B2,  # BOT2 teal
}

# Runtime template one — research/runtime-graphics-spec.md rectangles.
WELLS = {
    "left": {"x": 40, "y": 100, "w": 620, "h": 700},
    "right": {"x": 1260, "y": 100, "w": 620, "h": 700},
    "center": {"x": 660, "y": 100, "w": 600, "h": 700},
    "solo": {"x": 80, "y": 80, "w": 620, "h": 700},
}


def _item_source(item: object) -> str:
    if isinstance(item, dict):
        return str(item["sourceName"])
    return str(item.source_name)


def _item_id(item: object) -> int:
    if isinstance(item, dict):
        return int(item["sceneItemId"])
    return int(item.scene_item_id)


def _items(client: ReqClient, scene: str) -> list[tuple[str, int]]:
    response = client.get_scene_item_list(name=scene)
    raw = getattr(response, "scene_items", None) or []
    return [(_item_source(item), _item_id(item)) for item in raw]


def _ids(client: ReqClient, scene: str, source: str) -> list[int]:
    return [item_id for name, item_id in _items(client, scene) if name == source]


def _bounds(x: float, y: float, w: float, h: float, *, crop_left: int = 0, crop_right: int = 0) -> dict:
    return {
        "positionX": float(x),
        "positionY": float(y),
        "alignment": ALIGN_TOP_LEFT,
        "rotation": 0.0,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "boundsType": "OBS_BOUNDS_SCALE_OUTER",
        "boundsAlignment": ALIGN_TOP_LEFT,
        "boundsWidth": float(w),
        "boundsHeight": float(h),
        "cropLeft": int(crop_left),
        "cropRight": int(crop_right),
        "cropTop": 0,
        "cropBottom": 0,
    }


def ensure_sync_check(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size > 0:
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0:s=x",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as error:
            if path.resolve() != DEFAULT_CLIP.resolve():
                raise RuntimeError(f"unable to inspect clip: {path}") from error
        else:
            if probe.stdout.strip() == f"{SOURCE_W}x{SOURCE_H}":
                return path
            if path.resolve() != DEFAULT_CLIP.resolve():
                raise RuntimeError(
                    f"clip must be {SOURCE_W}x{SOURCE_H}: {path}"
                )
    filtergraph = (
        "color=c=0xcc2222:s=672x768:d=5:r=24[l];"
        "color=c=0x2244cc:s=672x768:d=5:r=24[r];"
        "[l][r]hstack=inputs=2,"
        "drawbox=x=0:y=0:w=1344:h=768:t=fill:c=white:enable='between(n,60,62)'"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            filtergraph,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-shortest",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _refuse_streaming(client: ReqClient) -> None:
    stream = client.get_stream_status()
    if bool(getattr(stream, "output_active", False)):
        raise RuntimeError("OBS is already streaming; refusing to continue")


def apply_layout(
    client: ReqClient,
    *,
    clip: Path,
    watchdog_url: str,
    record_dir: Path = DEFAULT_RECORD_DIR,
) -> dict:
    _refuse_streaming(client)
    created = setup_obs(client, watchdog_url=watchdog_url)
    client.set_video_settings(30, 1, CANVAS_W, CANVAS_H, CANVAS_W, CANVAS_H)
    record_dir = Path(record_dir).resolve()
    record_dir.mkdir(parents=True, exist_ok=True)
    client.set_record_directory(str(record_dir))

    left = WELLS["left"]
    right = WELLS["right"]
    center = WELLS["center"]
    solo = WELLS["solo"]

    wide_ids = _ids(client, "wide", "HOST_WIDE")
    if wide_ids:
        client.set_scene_item_transform(
            "wide",
            wide_ids[0],
            _bounds(0, 0, CANVAS_W, CANVAS_H),
        )

    split_ids = _ids(client, "split", "HOST_WIDE")
    if len(split_ids) != 2:
        raise RuntimeError(f"split HOST_WIDE count {len(split_ids)} != 2")
    # Creation order: first item is camera-left (BOT1), second is camera-right.
    client.set_scene_item_transform(
        "split",
        split_ids[0],
        _bounds(left["x"], left["y"], left["w"], left["h"], crop_right=HALF_W),
    )
    client.set_scene_item_transform(
        "split",
        split_ids[1],
        _bounds(right["x"], right["y"], right["w"], right["h"], crop_left=HALF_W),
    )
    center_ids = _ids(client, "split", "CENTER")
    if center_ids:
        client.set_scene_item_transform(
            "split",
            center_ids[0],
            _bounds(center["x"], center["y"], center["w"], center["h"]),
        )

    solo_l_ids = _ids(client, "solo_l", "HOST_WIDE")
    if solo_l_ids:
        client.set_scene_item_transform(
            "solo_l",
            solo_l_ids[0],
            _bounds(solo["x"], solo["y"], solo["w"], solo["h"], crop_right=HALF_W),
        )
    solo_r_ids = _ids(client, "solo_r", "HOST_WIDE")
    if solo_r_ids:
        client.set_scene_item_transform(
            "solo_r",
            solo_r_ids[0],
            _bounds(
                CANVAS_W - solo["w"] - solo["x"],
                solo["y"],
                solo["w"],
                solo["h"],
                crop_left=HALF_W,
            ),
        )

    client.set_current_scene_transition("Cut")
    client.set_input_settings(
        name="HOST_WIDE",
        settings={
            "is_local_file": True,
            "local_file": str(clip.resolve()),
            "looping": False,
            "restart_on_activate": True,
            "close_when_inactive": False,
            "clear_on_media_end": False,
            "hw_decode": False,
        },
        overlay=False,
    )
    try:
        client.set_input_mute(name="HOST_WIDE", muted=False)
    except Exception:
        pass
    # Color sources default to a 1920×1080 plate and would cover the desk.
    # Size them as 8px speaking bars and hide until set_speaking.
    for name, well, x in (
        ("HL_A", left, left["x"] - 8),
        ("HL_B", right, right["x"] + right["w"]),
    ):
        client.set_input_settings(
            name=name,
            settings={
                "width": 8,
                "height": int(well["h"]),
                "color": HIGHLIGHT_COLORS[name],
            },
            overlay=True,
        )
        for scene in ("wide", "split", "solo_l", "solo_r"):
            for item_id in _ids(client, scene, name):
                client.set_scene_item_transform(
                    scene,
                    item_id,
                    _bounds(x, well["y"], 8, well["h"]),
                )
                client.set_scene_item_enabled(scene, item_id, False)

    errors = validate_contract(client)
    if errors:
        raise RuntimeError(errors[0])

    _refuse_streaming(client)
    client.set_current_program_scene("split")

    return {
        "created": created,
        "clip": str(clip.resolve()),
        "record_directory": str(record_dir),
        "canvas": {"w": CANVAS_W, "h": CANVAS_H, "fps": 30},
        "source": {"w": SOURCE_W, "h": SOURCE_H},
        "split_host_wide_ids": split_ids,
        "shared_source": True,
        "streaming": False,
        "contract": "ok",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4455)
    parser.add_argument(
        "--clip",
        type=Path,
        default=DEFAULT_CLIP,
    )
    parser.add_argument("--record-dir", type=Path, default=DEFAULT_RECORD_DIR)
    parser.add_argument("--watchdog-url", default=DEFAULT_WATCHDOG_URL)
    args = parser.parse_args()
    password = os.environ.get("OBS_WEBSOCKET_PASSWORD")
    if not password:
        print("missing OBS_WEBSOCKET_PASSWORD", file=sys.stderr)
        return 2
    clip = ensure_sync_check(args.clip)
    client = ReqClient(host=args.host, port=args.port, password=password, timeout=5)
    summary = apply_layout(
        client,
        clip=clip,
        watchdog_url=args.watchdog_url,
        record_dir=args.record_dir,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
