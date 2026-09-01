"""Load PR #26 design mocks into this OBS box without merging that branch.

Extracts the identity overlay, mark cuts, and dither wash from
research/mocks/. Does not write assets/broadcast/. WASH is not a
contract input. Package A stays blocked on the relock.

The wash is OBS furniture. H3 only sees the 1344×768 wide shot (hero or
that take's last frame). Program-out never goes back into fal, so the
wash can drift without touching generation. --static freezes it for an
encode test.

identity-bracket.html is the review page (scroll it in a browser).
overlay-live.html is the 1920×1080 CG cut: transparent host wells,
mark + rail + names + card + chyron + ticker. WATCHDOG points at that.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from obsws_python import ReqClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "runtime-flight"))

from runtime_flight.obs_setup import (  # noqa: E402
    REQUIRED_INPUTS,
    REQUIRED_SCENES,
    validate_contract,
)

DESIGN_REPO = "toastfacek/desk-show-live"
DESIGN_REF = "claude/design-brief-search-i5q8vj"
WASH_REPO_PATH = "research/mocks/dither-wash.html"
WASH_SOURCE = "WASH"
OVERLAY_LIVE_NAME = "overlay-live.html"
OVERLAY_LIVE_JS_NAME = "overlay-live.js"
OVERLAY_EMBED_NAME = "tweet-embed.html"
OVERLAY_LIVE_SRC = Path(__file__).resolve().parent / "design-preview" / OVERLAY_LIVE_NAME
OVERLAY_LIVE_JS_SRC = Path(__file__).resolve().parent / "design-preview" / OVERLAY_LIVE_JS_NAME
OVERLAY_EMBED_SRC = Path(__file__).resolve().parent / "design-preview" / OVERLAY_EMBED_NAME
DEFAULT_PREVIEW_DIR = Path("/tmp/runtime-design-preview")
DEFAULT_PORT = 8766
CANVAS_W = 1920
CANVAS_H = 1080
ALIGN_TOP_LEFT = 5
ALIGN_CENTER = 0
SOURCE_W = 1344
SOURCE_H = 768
HALF_W = SOURCE_W // 2
# Measured on the locked Light Media Club two-shot: sprites sit near
# x=240 and x=1092, not the center of each 672px half. Tighter windows
# pan them into the wells instead of pinning them to the outer edges.
CROP_W = 500
CROP_TOP = 48
HOST_L_X = 240
HOST_R_X = 1092
HOST_WIDE_PLAYBACK = {
    "is_local_file": True,
    "looping": False,
    "restart_on_activate": False,
    "close_when_inactive": False,
    "clear_on_media_end": False,
    "hw_decode": False,
}
# identity-bracket.html "The frame" used y=140. The rail and sponsor sit at
# y=48 (60px tall), so that left only 32px under the logo / timer. Nudge
# the wells down 32px and shorten them so the chyron at y=838 stays clear.
DESIGN_WELLS = {
    "left": {"x": 64, "y": 172, "w": 580, "h": 628},
    "right": {"x": 1276, "y": 172, "w": 580, "h": 628},
    "center": {"x": 668, "y": 172, "w": 584, "h": 628},
}
# Overlay owns these. Leave the inputs; hide the scene items.
CONTRACT_FURNITURE = (
    "HEADLINE",
    "NAME_A",
    "NAME_B",
    "HL_A",
    "HL_B",
    "CENTER",
)
PREVIEW_REPO_FILES = (
    "research/mocks/dither-wash.html",
    "research/mocks/identity-bracket.html",
    "research/mocks/component-exploration.html",
    "research/mocks/direction-machined-glass.html",
    "research/mocks/mark/README.md",
    "research/mocks/mark/runtime-mark.svg",
    "research/mocks/mark/runtime-mark-mono.svg",
    "research/mocks/mark/runtime-mark-offair.svg",
    "research/mocks/mark/runtime-mark.txt",
    "research/mocks/mark/proof-16.png",
    "research/mocks/mark/proof-32.png",
    "research/mocks/mark/proof-72.png",
)

assert WASH_SOURCE not in REQUIRED_INPUTS
assert OVERLAY_LIVE_SRC.is_file()
assert OVERLAY_LIVE_JS_SRC.is_file()
assert OVERLAY_EMBED_SRC.is_file()


def wash_query(*, static: bool = False, speed: float = 1.0) -> str:
    params: dict[str, str] = {"static": "1" if static else "0"}
    if not static:
        params["speed"] = f"{speed:g}"
    return urlencode(params)


def wash_url(
    port: int,
    *,
    static: bool = False,
    speed: float = 1.0,
    host: str = "127.0.0.1",
) -> str:
    return (
        f"http://{host}:{int(port)}/dither-wash.html?"
        f"{wash_query(static=static, speed=speed)}"
    )


def overlay_live_url(
    port: int,
    *,
    speaker: str = "a",
    host: str = "127.0.0.1",
    card_origin: str | None = None,
) -> str:
    url = f"http://{host}:{int(port)}/{OVERLAY_LIVE_NAME}?speaker={speaker}"
    if card_origin:
        url += f"&card_origin={quote(card_origin, safe=':/')}"
    return url


def copy_overlay_live(dest: Path) -> dict[str, str]:
    dest.mkdir(parents=True, exist_ok=True)
    live = dest / OVERLAY_LIVE_NAME
    script = dest / OVERLAY_LIVE_JS_NAME
    embed = dest / OVERLAY_EMBED_NAME
    shutil.copyfile(OVERLAY_LIVE_SRC, live)
    shutil.copyfile(OVERLAY_LIVE_JS_SRC, script)
    shutil.copyfile(OVERLAY_EMBED_SRC, embed)
    return {
        OVERLAY_LIVE_NAME: str(live),
        OVERLAY_LIVE_JS_NAME: str(script),
        OVERLAY_EMBED_NAME: str(embed),
    }


def wash_browser_settings(url: str) -> dict:
    return {
        "url": url,
        "width": CANVAS_W,
        "height": CANVAS_H,
        "reroute_audio": False,
        "shutdown": False,
        "restart_when_active": False,
        "fps": 30,
        "fps_custom": True,
    }


def canvas_transform() -> dict:
    return _bounds(0, 0, CANVAS_W, CANVAS_H)


def host_crop(center_x: int, *, width: int = CROP_W, top: int = CROP_TOP) -> dict:
    width = min(int(width), SOURCE_W)
    left = int(center_x) - width // 2
    right = SOURCE_W - left - width
    if left < 0:
        right += left
        left = 0
    if right < 0:
        left += right
        right = 0
    return {
        "crop_left": max(0, left),
        "crop_right": max(0, right),
        "crop_top": max(0, min(int(top), SOURCE_H - 1)),
    }


def _bounds(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    crop_left: int = 0,
    crop_right: int = 0,
    crop_top: int = 0,
    bounds_alignment: int = ALIGN_CENTER,
) -> dict:
    return {
        "positionX": float(x),
        "positionY": float(y),
        "alignment": ALIGN_TOP_LEFT,
        "rotation": 0.0,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "boundsType": "OBS_BOUNDS_SCALE_OUTER",
        "boundsAlignment": int(bounds_alignment),
        "boundsWidth": float(w),
        "boundsHeight": float(h),
        "cropLeft": int(crop_left),
        "cropRight": int(crop_right),
        "cropTop": int(crop_top),
        "cropBottom": 0,
    }


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    sock = socket.socket()
    sock.settimeout(1)
    try:
        return sock.connect_ex((host, int(port))) == 0
    finally:
        sock.close()


def _refuse_streaming(client: ReqClient) -> None:
    stream = client.get_stream_status()
    if bool(getattr(stream, "output_active", False)):
        raise RuntimeError("OBS is already streaming; refusing to continue")


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


def _input_kinds(client: ReqClient) -> dict[str, str]:
    response = client.get_input_list()
    inputs = getattr(response, "inputs", None) or []
    kinds: dict[str, str] = {}
    for item in inputs:
        if isinstance(item, dict):
            name = item["inputName"]
            kind = item.get("unversionedInputKind") or item.get("inputKind")
        else:
            name = item.input_name
            kind = getattr(item, "unversioned_input_kind", None) or getattr(
                item, "input_kind", None
            )
        if kind:
            kinds[name] = str(kind)
    return kinds


def _fetch_github_file(repo_path: str, *, ref: str) -> bytes:
    payload = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{DESIGN_REPO}/contents/{repo_path}?ref={ref}",
            "--jq",
            ".content",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return base64.b64decode(payload)


def extract_preview(dest: Path, *, ref: str = DESIGN_REF) -> dict[str, str]:
    dest.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for repo_path in PREVIEW_REPO_FILES:
        rel = repo_path.split("research/mocks/", 1)[1]
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(_fetch_github_file(repo_path, ref=ref))
        written[rel] = str(out)
    if b"DITHER WASH" not in (dest / "dither-wash.html").read_bytes():
        raise RuntimeError("extracted file is not the dither-wash preview")
    if b"The overlay stops performing" not in (
        dest / "identity-bracket.html"
    ).read_bytes():
        raise RuntimeError("extracted file is not identity-bracket.html")
    written.update(copy_overlay_live(dest))
    return written


def extract_wash(dest: Path, *, ref: str = DESIGN_REF) -> Path:
    return Path(extract_preview(dest, ref=ref)["dither-wash.html"])


def serve_preview(dest: Path, port: int) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    pid_path = dest / "http.pid"
    log_path = dest / "http.log"
    if port_open(port):
        return {"port": port, "reused": True, "pid_path": str(pid_path)}
    handle = subprocess.Popen(
        [sys.executable, "-m", "http.server", "--bind", "127.0.0.1", str(port)],
        cwd=str(dest),
        stdout=log_path.open("a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_path.write_text(f"{handle.pid}\n", encoding="utf-8")
    for _ in range(40):
        if port_open(port):
            return {
                "port": port,
                "reused": False,
                "pid": handle.pid,
                "pid_path": str(pid_path),
            }
        time.sleep(0.05)
    raise RuntimeError(f"preview HTTP server did not bind :{port}")


def apply_wash(client: ReqClient, *, url: str) -> dict:
    _refuse_streaming(client)
    errors = validate_contract(client)
    if errors:
        raise RuntimeError(
            "OBS contract missing; run ./scripts/setup-obs-box.sh first: "
            + errors[0]
        )

    kinds = _input_kinds(client)
    browser_kind = kinds.get("WATCHDOG")
    if not browser_kind:
        raise RuntimeError("WATCHDOG browser source is missing")

    settings = wash_browser_settings(url)
    created_input = False
    if WASH_SOURCE not in kinds:
        client.create_input(
            sceneName="wide",
            inputName=WASH_SOURCE,
            inputKind=browser_kind,
            inputSettings=settings,
            sceneItemEnabled=True,
        )
        created_input = True
    else:
        client.set_input_settings(name=WASH_SOURCE, settings=settings, overlay=True)

    created_items: list[str] = []
    item_ids: dict[str, int] = {}
    transform = canvas_transform()
    for scene in REQUIRED_SCENES:
        ids = _ids(client, scene, WASH_SOURCE)
        if not ids:
            client.create_scene_item(scene, WASH_SOURCE, True)
            created_items.append(scene)
            ids = _ids(client, scene, WASH_SOURCE)
        if not ids:
            raise RuntimeError(f"failed to place {WASH_SOURCE} in {scene}")
        item_id = ids[0]
        item_ids[scene] = item_id
        client.set_scene_item_transform(scene, item_id, transform)
        client.set_scene_item_index(scene, item_id, 0)

    _refuse_streaming(client)
    return {
        "source": WASH_SOURCE,
        "url": url,
        "created_input": created_input,
        "created_scene_items": created_items,
        "item_ids": item_ids,
        "z_index": 0,
        "contract_input": False,
        "streaming": False,
    }


def apply_identity_overlay(client: ReqClient, *, url: str) -> dict:
    client.set_input_settings(
        name="WATCHDOG",
        settings=wash_browser_settings(url),
        overlay=True,
    )
    return {"source": "WATCHDOG", "url": url, "role": "identity-overlay"}


def apply_cut_transition(client: ReqClient) -> None:
    client.set_current_scene_transition("Cut")


def apply_host_wide_playback(client: ReqClient) -> None:
    client.set_input_settings(
        name="HOST_WIDE",
        settings=dict(HOST_WIDE_PLAYBACK),
        overlay=True,
    )
    try:
        client.set_input_mute(name="HOST_WIDE", muted=False)
    except Exception:
        pass


def apply_design_wells(client: ReqClient) -> dict:
    left = DESIGN_WELLS["left"]
    right = DESIGN_WELLS["right"]
    left_crop = host_crop(HOST_L_X)
    right_crop = host_crop(HOST_R_X)
    split_ids = _ids(client, "split", "HOST_WIDE")
    if len(split_ids) != 2:
        raise RuntimeError(f"split HOST_WIDE count {len(split_ids)} != 2")
    client.set_scene_item_transform(
        "split",
        split_ids[0],
        _bounds(left["x"], left["y"], left["w"], left["h"], **left_crop),
    )
    client.set_scene_item_transform(
        "split",
        split_ids[1],
        _bounds(right["x"], right["y"], right["w"], right["h"], **right_crop),
    )
    solo = left
    solo_l_ids = _ids(client, "solo_l", "HOST_WIDE")
    if solo_l_ids:
        client.set_scene_item_transform(
            "solo_l",
            solo_l_ids[0],
            _bounds(solo["x"], solo["y"], solo["w"], solo["h"], **left_crop),
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
                **right_crop,
            ),
        )
    return {
        "wells": DESIGN_WELLS,
        "split_host_wide_ids": split_ids,
        "crops": {"left": left_crop, "right": right_crop},
    }


def hide_contract_furniture(client: ReqClient) -> list[str]:
    hidden: list[str] = []
    for scene in REQUIRED_SCENES:
        for source in CONTRACT_FURNITURE:
            for item_id in _ids(client, scene, source):
                client.set_scene_item_enabled(scene, item_id, False)
                hidden.append(f"{scene}:{source}")
    return hidden


def apply_preview(
    client: ReqClient, *, wash: str, overlay: str
) -> dict:
    _refuse_streaming(client)
    apply_cut_transition(client)
    apply_host_wide_playback(client)
    summary = apply_wash(client, url=wash)
    identity = apply_identity_overlay(client, url=overlay)
    wells = apply_design_wells(client)
    hidden = hide_contract_furniture(client)
    _refuse_streaming(client)
    return {
        "wash": summary,
        "overlay": identity,
        "wells": wells,
        "hidden_furniture": hidden,
        "streaming": False,
        "transition": "Cut",
        "review_pages": [
            "identity-bracket.html",
            "component-exploration.html",
            "mark/runtime-mark.svg",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--obs-port", type=int, default=4455)
    parser.add_argument("--preview-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--preview-dir", type=Path, default=DEFAULT_PREVIEW_DIR)
    parser.add_argument("--ref", default=DESIGN_REF)
    parser.add_argument("--speaker", choices=("a", "b"), default="a")
    parser.add_argument(
        "--card-origin",
        default="",
        help="Loopback OverlayServer origin the live CG should poll for card.json.",
    )
    parser.add_argument(
        "--overlay-url",
        default="",
        help="Full WATCHDOG URL. Overrides preview-port overlay-live URL.",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="Freeze the wash (encode-safe). Default is drift behind the desk.",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Wash drift rate. Ignored with --static. HTML default is 1.",
    )
    parser.add_argument(
        "--drift",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Write the mock tree and overlay-live.html, then exit.",
    )
    parser.add_argument(
        "--serve-only",
        action="store_true",
        help="Extract if needed and serve; do not touch OBS.",
    )
    args = parser.parse_args()

    identity = args.preview_dir / "identity-bracket.html"
    live = args.preview_dir / OVERLAY_LIVE_NAME
    if not identity.is_file() or not live.is_file():
        extract_preview(args.preview_dir, ref=args.ref)
    else:
        copy_overlay_live(args.preview_dir)
    if args.extract_only:
        print(
            json.dumps(
                {
                    "dir": str(args.preview_dir),
                    "overlay": str(live),
                    "review": str(identity),
                },
                indent=2,
            )
        )
        return 0

    served = serve_preview(args.preview_dir, args.preview_port)
    wash = wash_url(
        args.preview_port, static=args.static, speed=args.speed
    )
    overlay = args.overlay_url or overlay_live_url(
        args.preview_port,
        speaker=args.speaker,
        card_origin=args.card_origin or None,
    )
    if args.serve_only:
        print(
            json.dumps(
                {"wash": wash, "overlay": overlay, "review": f"http://127.0.0.1:{args.preview_port}/identity-bracket.html", **served},
                indent=2,
            )
        )
        return 0

    password = os.environ.get("OBS_WEBSOCKET_PASSWORD")
    if not password:
        print("missing OBS_WEBSOCKET_PASSWORD", file=sys.stderr)
        return 2
    client = ReqClient(
        host=args.host, port=args.obs_port, password=password, timeout=5
    )
    summary = apply_preview(client, wash=wash, overlay=overlay)
    summary["preview"] = served
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
