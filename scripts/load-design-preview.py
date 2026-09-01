"""Load PR #26 dither-wash as a below-desk OBS Browser Source.

Does not merge the design branch. Does not write assets/broadcast/.
Does not add WASH to the scene contract. Package A stays blocked on the
relock in research/deliverables/RELOCK_PROPOSAL.md.

The only OBS-ready file in that PR is research/mocks/dither-wash.html.
identity-bracket.html is a scrollable review page, not live CG — do not
point WATCHDOG at it. Live CG remains runtime-flight/overlay on :8765.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

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
DEFAULT_PREVIEW_DIR = Path("/tmp/runtime-design-preview")
DEFAULT_PORT = 8766
CANVAS_W = 1920
CANVAS_H = 1080
ALIGN_TOP_LEFT = 5

assert WASH_SOURCE not in REQUIRED_INPUTS


def wash_query(*, static: bool = True) -> str:
    # On-air setting from the HTML header: frozen wash behind hosts.
    return urlencode({"static": "1" if static else "0"})


def wash_url(port: int, *, static: bool = True, host: str = "127.0.0.1") -> str:
    return f"http://{host}:{int(port)}/dither-wash.html?{wash_query(static=static)}"


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
    return {
        "positionX": 0.0,
        "positionY": 0.0,
        "alignment": ALIGN_TOP_LEFT,
        "rotation": 0.0,
        "scaleX": 1.0,
        "scaleY": 1.0,
        "boundsType": "OBS_BOUNDS_SCALE_OUTER",
        "boundsAlignment": ALIGN_TOP_LEFT,
        "boundsWidth": float(CANVAS_W),
        "boundsHeight": float(CANVAS_H),
        "cropLeft": 0,
        "cropRight": 0,
        "cropTop": 0,
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


def extract_wash(dest: Path, *, ref: str = DESIGN_REF) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "dither-wash.html"
    payload = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{DESIGN_REPO}/contents/{WASH_REPO_PATH}?ref={ref}",
            "--jq",
            ".content",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    html = base64.b64decode(payload)
    if b"DITHER WASH" not in html:
        raise RuntimeError("extracted file is not the dither-wash preview")
    out.write_bytes(html)
    return out


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--obs-port", type=int, default=4455)
    parser.add_argument("--preview-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--preview-dir", type=Path, default=DEFAULT_PREVIEW_DIR)
    parser.add_argument("--ref", default=DESIGN_REF)
    parser.add_argument(
        "--drift",
        action="store_true",
        help="Allow wash drift. Default is ?static=1 (on-air).",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Write dither-wash.html and exit.",
    )
    parser.add_argument(
        "--serve-only",
        action="store_true",
        help="Extract if needed and serve; do not touch OBS.",
    )
    args = parser.parse_args()

    html = args.preview_dir / "dither-wash.html"
    if not html.is_file():
        html = extract_wash(args.preview_dir, ref=args.ref)
    if args.extract_only:
        print(json.dumps({"path": str(html)}, indent=2))
        return 0

    served = serve_preview(args.preview_dir, args.preview_port)
    url = wash_url(args.preview_port, static=not args.drift)
    if args.serve_only:
        print(json.dumps({"url": url, **served}, indent=2))
        return 0

    password = os.environ.get("OBS_WEBSOCKET_PASSWORD")
    if not password:
        print("missing OBS_WEBSOCKET_PASSWORD", file=sys.stderr)
        return 2
    client = ReqClient(
        host=args.host, port=args.obs_port, password=password, timeout=5
    )
    summary = apply_wash(client, url=url)
    summary["preview"] = served
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
