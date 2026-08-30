"""In-memory player. Time is owned by the harness."""


class FakePlayer:
    def __init__(self) -> None:
        self.t = 0.0
        self.layout = "hold"
        self.connected = True
        self.headline = ""
        self.speaking = None
        self.center_kind = "none"
        self.center_data: dict | None = None
        self.calls: list[tuple] = []
        self._path: str | None = None
        self._clip_started_at: float | None = None
        self._duration_s = 5.0

    def get_program_state(self) -> dict:
        on_air = None
        if self._path and self._clip_started_at is not None:
            ends_at = self._clip_started_at + self._duration_s
            on_air = {
                "kind": "host",
                "path": self._path,
                "take": None,
                "duration_s": self._duration_s,
                "ends_at": ends_at,
                "media_ok": True,
            }
        return {
            "t": self.t,
            "layout": self.layout,
            "on_air": on_air,
            "connected": self.connected,
        }

    def set_layout(self, name: str) -> None:
        self.calls.append(("set_layout", name))
        self.layout = name

    def play_clip(self, path: str) -> None:
        self.calls.append(("play_clip", path))
        self._path = path
        self._clip_started_at = self.t

    def set_speaking(self, host: str | None) -> None:
        self.calls.append(("set_speaking", host))
        self.speaking = host

    def set_center(self, kind: str, data: dict | None) -> None:
        self.calls.append(("set_center", kind, data))
        self.center_kind = kind
        self.center_data = data

    def set_headline(self, text: str) -> None:
        self.calls.append(("set_headline", text))
        self.headline = text

    def set_name_bar(self, host: str, name: str, handle: str) -> None:
        self.calls.append(("set_name_bar", host, name, handle))

    def duck_music(self, db: float) -> None:
        self.calls.append(("duck_music", db))

    def set_clip_duration(self, seconds: float) -> None:
        self._duration_s = seconds
