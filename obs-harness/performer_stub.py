"""Copy a local clip after a fake delay. Never talks to a video vendor."""

from pathlib import Path


class StubPerformer:
    def __init__(
        self,
        clip_pool: Path,
        ready_dir: Path,
        delay_s: float = 4.0,
        delay_jitter_s: float = 0.0,
        forced_late_takes: list[int] | None = None,
        forced_late_delay_s: float = 8.0,
        clip_duration_s: float = 5.0,
    ) -> None:
        self.clip_pool = Path(clip_pool)
        self.ready_dir = Path(ready_dir)
        self.ready_dir.mkdir(parents=True, exist_ok=True)
        self.delay_s = delay_s
        self.delay_jitter_s = delay_jitter_s
        self.forced_late_takes = set(forced_late_takes or [])
        self.forced_late_delay_s = forced_late_delay_s
        self.clip_duration_s = clip_duration_s
        self._pool = sorted(self.clip_pool.glob("*.mp4"))
        if not self._pool:
            raise FileNotFoundError(f"no mp4 files in {clip_pool}")
        self._i = 0

    def delay_for(self, take: int) -> float:
        if take in self.forced_late_takes:
            return self.forced_late_delay_s
        return self.delay_s

    def materialize(self, submit: dict) -> dict:
        src = self._pool[self._i % len(self._pool)]
        self._i += 1
        take = submit["take"]
        dest = self.ready_dir / f"{take:03d}.mp4"
        dest.write_bytes(src.read_bytes())
        return {
            "take": take,
            "path": str(dest.resolve()),
            "speaker": submit.get("speaker"),
            "line": submit.get("line"),
            "duration_s": self.clip_duration_s,
            "forced_late": take in self.forced_late_takes,
        }
