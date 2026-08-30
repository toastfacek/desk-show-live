#!/usr/bin/env python3
"""One-shot desk setup. Builds the six Runtime scenes in the current OBS collection.

The show loop never calls this. Code on air may only switch and fill.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYOUTS = ("wide", "split", "solo_l", "solo_r", "card_full", "hold")

PAD = 32
STAGE_TOP = 96
STAGE_H = 792
COL = (1920 - PAD * 2) / 3
SOLO_HOST = 1200
SOLO_INFO = 656


def connect(host: str, port: int, password: str):
    try:
        from obsws_python import ReqClient
    except ImportError:
        print("pip install 'obsws-python>=1.7'", file=sys.stderr)
        raise SystemExit(2)
    return ReqClient(host=host, port=port, password=password, timeout=5)


def _names(items, name_key: str, alt: str) -> set[str]:
    out = set()
    for item in items or []:
        if isinstance(item, dict):
            out.add(item.get(name_key) or item.get(alt) or "")
        else:
            out.add(getattr(item, alt, "") or getattr(item, name_key, "") or "")
    return out


def scene_names(client) -> set[str]:
    return _names(client.get_scene_list().scenes, "sceneName", "scene_name")


def input_names(client) -> set[str]:
    return _names(client.get_input_list().inputs, "inputName", "input_name")


def kind_list(client) -> set[str]:
    raw = client.get_input_kind_list()
    kinds = getattr(raw, "input_kinds", None) or getattr(raw, "inputKinds", None) or []
    return set(kinds)


def pick_kind(kinds: set[str], candidates: tuple[str, ...]) -> str:
    for name in candidates:
        if name in kinds:
            return name
    return candidates[0]


def ensure_scene(client, name: str) -> None:
    if name not in scene_names(client):
        client.create_scene(name)


def ensure_input(client, scene: str, name: str, kind: str, settings: dict) -> None:
    if name in input_names(client):
        return
    client.create_input(scene, name, kind, settings, True)


def item_id(client, scene: str, source: str) -> int | None:
    raw = client.get_scene_item_list(name=scene)
    items = getattr(raw, "scene_items", None) or getattr(raw, "sceneItems", None) or []
    for item in items:
        if isinstance(item, dict):
            src = item.get("sourceName") or item.get("source_name")
            ident = item.get("sceneItemId") or item.get("scene_item_id")
        else:
            src = getattr(item, "source_name", None) or getattr(item, "sourceName", None)
            ident = getattr(item, "scene_item_id", None) or getattr(item, "sceneItemId", None)
        if src == source:
            return int(ident)
    return None


def ensure_item(client, scene: str, source: str, enabled: bool = True) -> int:
    ident = item_id(client, scene, source)
    if ident is None:
        client.create_scene_item(scene_name=scene, source_name=source, enabled=enabled)
        ident = item_id(client, scene, source)
    if ident is None:
        raise RuntimeError(f"could not add {source} to {scene}")
    client.set_scene_item_enabled(scene_name=scene, item_id=ident, enabled=enabled)
    return ident


def place(client, scene: str, source: str, x: float, y: float, w: float, h: float, crop_left=0, crop_right=0, enabled=True) -> None:
    ident = ensure_item(client, scene, source, enabled=enabled)
    client.set_scene_item_transform(
        scene_name=scene,
        item_id=ident,
        transform={
            "positionX": x,
            "positionY": y,
            "alignment": 5,
            "boundsType": "OBS_BOUNDS_SCALE_INNER",
            "boundsAlignment": 5,
            "boundsWidth": w,
            "boundsHeight": h,
            "cropLeft": crop_left,
            "cropRight": crop_right,
            "cropTop": 0,
            "cropBottom": 0,
        },
    )


def host_width(client, scene: str) -> int:
    ident = item_id(client, scene, "HOST_WIDE")
    if ident is None:
        return 1344
    raw = client.get_scene_item_transform(scene_name=scene, item_id=ident)
    tr = getattr(raw, "scene_item_transform", None) or getattr(raw, "sceneItemTransform", None) or raw
    if isinstance(tr, dict):
        return int(tr.get("sourceWidth") or tr.get("source_width") or 1344)
    return int(getattr(tr, "sourceWidth", 0) or getattr(tr, "source_width", 0) or 1344)


def install(client, overlay_url: str, clip: Path) -> None:
    kinds = kind_list(client)
    text_kind = pick_kind(kinds, ("text_gdiplus_v2", "text_ft2_source_v2", "text_ft2_source"))
    color_kind = pick_kind(kinds, ("color_source_v3", "color_source"))
    media_kind = pick_kind(kinds, ("ffmpeg_source",))
    browser_kind = pick_kind(kinds, ("browser_source",))

    for name in LAYOUTS:
        ensure_scene(client, name)

    home = "wide"
    ensure_input(
        client,
        home,
        "HOST_WIDE",
        media_kind,
        {
            "local_file": str(clip.resolve()),
            "is_local_file": True,
            "looping": False,
            "restart_on_activate": False,
        },
    )
    ensure_input(
        client,
        home,
        "FRAME",
        browser_kind,
        {
            "url": overlay_url,
            "width": 1920,
            "height": 1080,
            "reroute_audio": False,
            "shutdown": False,
            "restart_when_active": False,
        },
    )
    ensure_input(client, home, "CENTER", color_kind, {"color": 0xFF0C1016, "width": 8, "height": 8})
    ensure_input(client, home, "HEADLINE", text_kind, {"text": "A MOVE WITHOUT A THESIS"})
    ensure_input(client, home, "NAME_A", text_kind, {"text": "PHASEONE[lol]"})
    ensure_input(client, home, "NAME_B", text_kind, {"text": "deb"})
    ensure_input(client, home, "HL_A", color_kind, {"color": 0xFFF0A33C, "width": 8, "height": 8})
    ensure_input(client, home, "HL_B", color_kind, {"color": 0xFF3EE0E8, "width": 8, "height": 8})
    ensure_input(client, home, "BED", media_kind, {"is_local_file": True, "local_file": ""})

    src_w = host_width(client, home)
    half = max(1, src_w // 2)
    right_x = PAD + 2 * COL
    solo_r_x = PAD + SOLO_INFO

    for scene in LAYOUTS:
        place(client, scene, "FRAME", 0, 0, 1920, 1080, enabled=True)
        host_on = scene in ("wide", "split", "solo_l", "solo_r")
        if scene == "wide":
            place(client, scene, "HOST_WIDE", PAD, STAGE_TOP, 1920 - PAD * 2, STAGE_H, enabled=True)
        elif scene == "split":
            place(client, scene, "HOST_WIDE", PAD, STAGE_TOP, COL, STAGE_H, crop_right=half, enabled=True)
            # Second item of the same source — shared playhead.
            left_id = item_id(client, scene, "HOST_WIDE")
            items = getattr(client.get_scene_item_list(name=scene), "scene_items", None) or []
            host_items = [
                it for it in items
                if (it.get("sourceName") if isinstance(it, dict) else getattr(it, "source_name", "")) == "HOST_WIDE"
            ]
            if len(host_items) < 2:
                client.create_scene_item(scene_name=scene, source_name="HOST_WIDE", enabled=True)
            place(client, scene, "HOST_WIDE", right_x, STAGE_TOP, COL, STAGE_H, crop_left=half, enabled=True)
            # place() updates the first matching item. Pin both explicitly.
            ids = []
            raw_items = getattr(client.get_scene_item_list(name=scene), "scene_items", None) or []
            for it in raw_items:
                name = it.get("sourceName") if isinstance(it, dict) else getattr(it, "source_name", "")
                ident = it.get("sceneItemId") if isinstance(it, dict) else getattr(it, "scene_item_id", None)
                if name == "HOST_WIDE":
                    ids.append(int(ident))
            if len(ids) >= 2:
                client.set_scene_item_transform(
                    scene_name=scene,
                    item_id=ids[0],
                    transform={
                        "positionX": PAD,
                        "positionY": STAGE_TOP,
                        "alignment": 5,
                        "boundsType": "OBS_BOUNDS_SCALE_INNER",
                        "boundsAlignment": 5,
                        "boundsWidth": COL,
                        "boundsHeight": STAGE_H,
                        "cropLeft": 0,
                        "cropRight": half,
                    },
                )
                client.set_scene_item_transform(
                    scene_name=scene,
                    item_id=ids[1],
                    transform={
                        "positionX": right_x,
                        "positionY": STAGE_TOP,
                        "alignment": 5,
                        "boundsType": "OBS_BOUNDS_SCALE_INNER",
                        "boundsAlignment": 5,
                        "boundsWidth": COL,
                        "boundsHeight": STAGE_H,
                        "cropLeft": half,
                        "cropRight": 0,
                    },
                )
            _ = left_id
        elif scene == "solo_l":
            place(client, scene, "HOST_WIDE", PAD, STAGE_TOP, SOLO_HOST, STAGE_H, crop_right=half, enabled=True)
        elif scene == "solo_r":
            place(client, scene, "HOST_WIDE", solo_r_x, STAGE_TOP, SOLO_HOST, STAGE_H, crop_left=half, enabled=True)
        else:
            place(client, scene, "HOST_WIDE", PAD, STAGE_TOP, COL, STAGE_H, enabled=host_on)

    client.set_current_program_scene("hold")
    print("Runtime scenes are in the current OBS collection.")
    print(f"FRAME loads {overlay_url}")
    print("Start the overlay server, then: python3 run.py --player obs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Runtime scenes into stock OBS")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4455)
    parser.add_argument("--overlay-url", default="http://127.0.0.1:8765/graphics/overlay.html")
    parser.add_argument(
        "--clip",
        default=str(ROOT / "assets" / "clips" / "sync_check.mp4"),
    )
    args = parser.parse_args(argv)
    password = os.environ.get("OBS_WEBSOCKET_PASSWORD", "")
    try:
        client = connect(args.host, args.port, password)
    except Exception as exc:
        print(f"OBS not connected: {exc}", file=sys.stderr)
        return 2
    clip = Path(args.clip)
    if not clip.exists():
        print(f"clip missing: {clip}", file=sys.stderr)
        return 2
    install(client, args.overlay_url, clip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
