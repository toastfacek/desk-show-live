"""OBS backend. Optional at import time; connect() talks to stock OBS."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


LAYOUTS = ("wide", "split", "solo_l", "solo_r", "card_full", "hold")
HOST_LAYOUTS = ("wide", "split", "solo_l", "solo_r")
HIGHLIGHT_SOURCES = ("HL_A", "HL_B")
HOST_WIDE_PLAYBACK = {
    "is_local_file": True,
    "looping": False,
    "restart_on_activate": False,
    "close_when_inactive": False,
    "clear_on_media_end": False,
    "hw_decode": False,
}


def prepare_obs_clip(path: str | Path) -> Path:
    """Remux H3 Constrained Baseline into High@3.2 so ffmpeg_source paints.

    Fal's ready files are valid media; this box's OBS source goes black on
    them. Evidence keeps the original. Playback uses a sibling `.obs.mp4`.
    """
    src = Path(path)
    dest = src.with_name(f"{src.stem}.obs{src.suffix}")
    if (
        dest.is_file()
        and dest.stat().st_size > 0
        and dest.stat().st_mtime >= src.stat().st_mtime
    ):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp.mp4")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-c:v",
                "libx264",
                "-profile:v",
                "high",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(tmp),
            ],
            check=True,
            capture_output=True,
        )
        os.replace(tmp, dest)
        return dest
    except (OSError, subprocess.CalledProcessError):
        tmp.unlink(missing_ok=True)
        return src


class ObsPlayer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4455,
        password: str | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password if password is not None else os.environ.get(
            "OBS_WEBSOCKET_PASSWORD", ""
        )
        self._client = None
        self.t = 0.0
        self.layout = "hold"
        self._scene_item_ids: dict[str, dict[str, int]] = {}

    def connect(self) -> None:
        try:
            from obsws_python import ReqClient
        except ImportError as exc:
            raise RuntimeError(
                "obsws-python is not installed. pip install obsws-python"
            ) from exc
        self._client = ReqClient(
            host=self.host, port=self.port, password=self.password, timeout=3
        )
        self._refresh_scene_item_cache()

    def _req(self):
        if self._client is None:
            raise RuntimeError("OBS is not connected")
        return self._client

    def _scene_item_id(self, item: object) -> int:
        if isinstance(item, dict):
            return int(item["sceneItemId"])
        return int(item.scene_item_id)

    def _source_name(self, item: object) -> str:
        if isinstance(item, dict):
            return str(item["sourceName"])
        return str(item.source_name)

    def _refresh_scene_item_cache(self) -> None:
        client = self._req()
        cache: dict[str, dict[str, int]] = {}
        for scene in LAYOUTS:
            response = client.get_scene_item_list(name=scene)
            items = getattr(response, "scene_items", None) or []
            mapping: dict[str, int] = {}
            for item in items:
                source_name = self._source_name(item)
                if source_name in HIGHLIGHT_SOURCES:
                    mapping[source_name] = self._scene_item_id(item)
            cache[scene] = mapping
        self._scene_item_ids = cache

    def get_program_state(self) -> dict:
        client = self._req()
        scene = client.get_current_program_scene().current_program_scene_name
        media_ok = True
        on_air = None
        try:
            status = client.get_media_input_status(name="HOST_WIDE")
            duration = getattr(status, "media_duration", None)
            cursor = getattr(status, "media_cursor", None)
            if duration is None or cursor is None:
                remaining_s = 0.0
            else:
                remaining = duration - cursor
                remaining_s = max(0.0, remaining / 1000.0) if remaining else 0.0
            on_air = {
                "kind": "host" if scene in HOST_LAYOUTS else "card",
                "path": None,
                "take": None,
                "duration_s": None,
                "ends_at": self.t + remaining_s,
                "media_ok": True,
            }
        except Exception:
            media_ok = False
            on_air = {
                "kind": "none",
                "path": None,
                "take": None,
                "duration_s": None,
                "ends_at": None,
                "media_ok": False,
            }
        return {
            "t": self.t,
            "layout": scene,
            "on_air": on_air,
            "connected": True,
            "media_ok": media_ok,
        }

    def set_layout(self, name: str) -> None:
        if name not in LAYOUTS:
            raise ValueError(f"unknown layout {name}")
        client = self._req()
        current = client.get_current_program_scene().current_program_scene_name
        if current != name:
            client.set_current_program_scene(name)
        self.layout = name

    def play_clip(self, path: str) -> None:
        client = self._req()
        playable = str(prepare_obs_clip(path))
        client.set_input_settings(
            name="HOST_WIDE",
            settings={"local_file": playable, **HOST_WIDE_PLAYBACK},
            overlay=True,
        )
        try:
            client.set_input_mute(name="HOST_WIDE", muted=False)
        except Exception:
            pass
        try:
            client.trigger_media_input_action(
                name="HOST_WIDE",
                action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
            )
        except Exception:
            pass

    def set_speaking(self, host: str | None) -> None:
        client = self._req()
        visibility = {
            "HL_A": host == "host_a",
            "HL_B": host == "host_b",
        }
        for scene in HOST_LAYOUTS:
            scene_ids = self._scene_item_ids.get(scene, {})
            for source_name, enabled in visibility.items():
                item_id = scene_ids.get(source_name)
                if item_id is None:
                    continue
                client.set_scene_item_enabled(scene, item_id, enabled)

    def set_center(self, kind: str, data: dict | None) -> None:
        _ = (kind, data)
        self._req()

    def set_headline(self, text: str) -> None:
        self._req().set_input_settings(
            name="HEADLINE", settings={"text": text}, overlay=True
        )

    def set_name_bar(self, host: str, name: str, handle: str) -> None:
        input_name = "NAME_A" if host == "host_a" else "NAME_B"
        self._req().set_input_settings(
            name=input_name,
            settings={"text": f"{name} {handle}".strip()},
            overlay=True,
        )

    def duck_music(self, db: float) -> None:
        mul = 10 ** (db / 20.0)
        try:
            self._req().set_input_volume(name="BED", vol_mul=mul)
        except Exception:
            pass

    def reconnect(self, deadline_s: float = 30.0) -> None:
        delay = 1.0
        start = time.monotonic()
        last_err = None
        while time.monotonic() - start < deadline_s:
            try:
                self.connect()
                return
            except Exception as exc:
                last_err = exc
                time.sleep(delay)
                delay = min(8.0, delay * 2)
        raise RuntimeError(f"OBS did not come back: {last_err}")
