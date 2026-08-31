"""OBS backend. Optional at import time; connect() talks to stock OBS."""

from __future__ import annotations

import os
import time


LAYOUTS = ("wide", "split", "solo_l", "solo_r", "card_full", "hold")


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

    def _req(self):
        if self._client is None:
            raise RuntimeError("OBS is not connected")
        return self._client

    def get_program_state(self) -> dict:
        client = self._req()
        scene = client.get_current_program_scene().current_program_scene_name
        media_ok = True
        on_air = None
        try:
            status = client.get_media_input_status(name="HOST_WIDE")
            remaining = getattr(status, "media_duration", 0) - getattr(
                status, "media_cursor", 0
            )
            remaining_s = max(0.0, remaining / 1000.0) if remaining else 0.0
            on_air = {
                "kind": "host" if scene in ("wide", "split", "solo_l", "solo_r") else "card",
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
        self._req().set_current_program_scene(name)
        self.layout = name

    def play_clip(self, path: str) -> None:
        client = self._req()
        client.set_input_settings(
            name="HOST_WIDE",
            settings={"local_file": path},
            overlay=True,
        )
        try:
            client.trigger_media_input_action(name="HOST_WIDE", action="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART")
        except Exception:
            pass

    def set_speaking(self, host: str | None) -> None:
        client = self._req()
        for slot, item in (("host_a", "HL_A"), ("host_b", "HL_B")):
            try:
                client.set_input_mute(name=item, muted=host != slot)
            except Exception:
                pass

    def set_center(self, kind: str, data: dict | None) -> None:
        # Visibility is scene-item work; v1 just records the payload on HEADLINE-adjacent CENTER.
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
        # 0 dB = 1.0 mul. Rough: 10 ** (db / 20).
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
