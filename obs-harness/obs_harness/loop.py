"""Short loop. The harness is the clock."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .director import decide
from .performer_stub import StubPerformer
from .player_fake import FakePlayer


class Harness:
    def __init__(
        self,
        rundown: dict,
        script_lines: list[dict],
        stub: StubPerformer,
        player: FakePlayer,
        clip_duration_s: float = 5.0,
        base_dir: Path | None = None,
    ) -> None:
        self.rundown = rundown
        self.script_lines = list(script_lines)
        self.script_i = 0
        self.stub = stub
        self.player = player
        self.clip_duration_s = clip_duration_s
        self.base_dir = Path(base_dir or ".")
        self.t = 0.0
        self.written_ahead: list[dict] = []
        self.ready: list[dict] = []
        self.cooking: dict | None = None
        self.on_air: dict | None = None
        self.next_take = 1
        self.layout_i = 0
        self.flags = {"hold": False, "panic": False}
        self.log: list[dict] = []
        self.beats: list[dict] = []
        self.after_step = None
        self.done = False
        self._refill_script()
        self.segment = rundown["segments"][0]
        self.package = self.segment["package"]

    @classmethod
    def from_rundown(
        cls,
        rundown_path: Path,
        stub: dict | None = None,
        clip_duration_s: float = 5.0,
        player: FakePlayer | None = None,
    ) -> Harness:
        rundown_path = Path(rundown_path)
        data = yaml.safe_load(rundown_path.read_text())
        base = rundown_path.parent
        script_path = Path(data["script_file"])
        if not script_path.is_absolute():
            script_path = base / script_path
        lines = [
            json.loads(line)
            for line in script_path.read_text().splitlines()
            if line.strip()
        ]
        clip_pool = Path(data["clip_pool"])
        if not clip_pool.is_absolute():
            clip_pool = base / clip_pool
        stub_cfg = stub or {}
        performer = StubPerformer(
            clip_pool=clip_pool,
            ready_dir=base / "out" / "ready",
            delay_s=stub_cfg.get("delay_s", 4.0),
            delay_jitter_s=stub_cfg.get("delay_jitter_s", 0.0),
            forced_late_takes=stub_cfg.get("forced_late_takes") or [],
            forced_late_delay_s=stub_cfg.get("forced_late_delay_s", 8.0),
            clip_duration_s=clip_duration_s,
        )
        fake = player or FakePlayer()
        fake.set_clip_duration(clip_duration_s)
        return cls(
            rundown=data,
            script_lines=lines,
            stub=performer,
            player=fake,
            clip_duration_s=clip_duration_s,
            base_dir=base,
        )

    def _refill_script(self) -> None:
        while len(self.written_ahead) < 2 and self.script_i < len(self.script_lines):
            self.written_ahead.append(self.script_lines[self.script_i])
            self.script_i += 1

    def snapshot(self) -> dict:
        next_line = self.written_ahead[0] if self.written_ahead else None
        return {
            "t": self.t,
            "on_air": (
                {
                    "layout": self.player.layout,
                    "take": self.on_air.get("take") if self.on_air else None,
                    "duration_s": self.clip_duration_s,
                    "ends_at": self.on_air.get("ends_at") if self.on_air else None,
                    "speaker": self.on_air.get("speaker") if self.on_air else None,
                }
                if self.on_air and self.on_air.get("kind") == "host"
                else self.on_air
            ),
            "ready": list(self.ready),
            "cooking": (
                {"take": self.cooking["take"], "submitted_at": self.cooking["submitted_at"]}
                if self.cooking
                else None
            ),
            "chain_ready": self.cooking is None,
            "next_line": (
                {"speaker": next_line["speaker"], "text": next_line["text"]}
                if next_line
                else None
            ),
            "spend_usd": 0.0,
            "spend_cap_usd": 20.0,
            "holds_recent": 0,
            "flags": dict(self.flags),
            "next_take": self.next_take,
            "layout_i": self.layout_i,
            "segment": {
                "layout_plan": self.segment.get("layout_plan") or ["wide"],
                "center": self.package.get("center") or {"kind": "none"},
                "chyron": self.package.get("chyron") or "",
                "spend_policy": self.package.get("spend_policy") or "normal",
            },
        }

    def _finish_cooking(self) -> None:
        if not self.cooking or self.t < self.cooking["ready_at"]:
            return
        clip = self.stub.materialize(self.cooking["submit"])
        clip["t_ready"] = self.t
        self.ready.append(clip)
        row = self._row(clip["take"])
        row["clip"] = clip["path"]
        row["t_ready"] = self.t
        row["status"] = "late" if self.cooking.get("missed_cut") else "ready"
        row["forced_late"] = clip["forced_late"]
        self.cooking = None

    def _row(self, take: int) -> dict:
        for row in self.log:
            if row["take"] == take:
                return row
        row = {
            "take": take,
            "line": None,
            "speaker": None,
            "clip": None,
            "status": "ready",
            "layout_on_air": None,
            "t_submit": None,
            "t_ready": None,
            "t_on_air": None,
            "delay_s": None,
            "forced_late": False,
            "cost_usd": 0.0,
        }
        self.log.append(row)
        return row

    def _should_cut(self) -> bool:
        if self.done:
            return False
        if self.flags.get("panic"):
            if self.on_air and self.on_air.get("kind") == "host":
                ends = self.on_air.get("ends_at")
                if ends is not None and self.t + 1e-9 < ends:
                    return False
            return True
        if self.on_air is None:
            return True
        ends = self.on_air.get("ends_at")
        if ends is not None and self.t + 1e-9 >= ends:
            return True
        if self.on_air.get("kind") != "host" and self.ready:
            return True
        return False

    def _execute(self, beat: dict) -> None:
        self.player.t = self.t
        self.player.set_layout(beat["layout"])
        self.player.set_headline(beat.get("chyron") or "")
        center = beat.get("center") or {"kind": "none"}
        self.player.set_center(center.get("kind") or "none", center)
        self.player.set_speaking(beat.get("speaking"))
        self.player.duck_music(-6.0 if beat.get("speaking") else 0.0)

        if beat.get("host_source"):
            take = int(str(beat["host_source"]).split(":")[1])
            clip = next(c for c in self.ready if c["take"] == take)
            self.ready = [c for c in self.ready if c["take"] != take]
            self.player.play_clip(clip["path"])
            self.on_air = {
                "kind": "host",
                "take": take,
                "speaker": clip.get("speaker"),
                "ends_at": self.t + clip.get("duration_s", self.clip_duration_s),
                "path": clip["path"],
            }
            self.layout_i += 1
            row = self._row(take)
            row["t_on_air"] = self.t
            row["layout_on_air"] = beat["layout"]
            row["line"] = clip.get("line")
            row["speaker"] = clip.get("speaker")
            if row["status"] not in ("late",):
                row["status"] = "ready"
        elif beat.get("submit"):
            self.on_air = {
                "kind": "card" if beat["layout"] == "card_full" else "hold",
                "take": None,
                "ends_at": None,
            }
        else:
            if beat.get("why") == "panic" or (
                beat["layout"] == "hold" and not self.ready and not self.cooking
            ):
                self.done = True
            self.on_air = {
                "kind": "hold" if beat["layout"] == "hold" else "card",
                "take": None,
                "ends_at": None,
            }

        if beat.get("submit"):
            submit = beat["submit"]
            delay = self.stub.delay_for(submit["take"])
            self.cooking = {
                "take": submit["take"],
                "submitted_at": self.t,
                "ready_at": self.t + delay,
                "submit": submit,
                "missed_cut": False,
            }
            row = self._row(submit["take"])
            row["line"] = submit.get("line")
            row["speaker"] = submit.get("speaker")
            row["t_submit"] = self.t
            row["delay_s"] = delay
            row["forced_late"] = submit["take"] in self.stub.forced_late_takes
            if self.written_ahead:
                self.written_ahead.pop(0)
            self._refill_script()
            self.next_take = submit["take"] + 1

    def step(self) -> None:
        self.player.t = self.t
        self._finish_cooking()
        if self.cooking and self.on_air and self.on_air.get("kind") == "host":
            ends = self.on_air.get("ends_at")
            if ends is not None and self.t + 1e-9 >= ends:
                self.cooking["missed_cut"] = True
        if self._should_cut():
            beat = decide(self.snapshot())
            self.beats.append(beat)
            self._execute(beat)
        if self.after_step:
            self.after_step()

    def run_simulated(self, until_takes_on_air: int | None = None, max_t: float = 90.0) -> None:
        self.step()
        while self.t < max_t and not self.done:
            next_t = self.t + 0.2
            if self.cooking:
                next_t = min(next_t, self.cooking["ready_at"])
            if self.on_air and self.on_air.get("ends_at") is not None:
                next_t = min(next_t, self.on_air["ends_at"])
            if next_t <= self.t:
                next_t = self.t + 0.2
            self.t = next_t
            self.step()
            aired = sum(1 for row in self.log if row.get("t_on_air") is not None)
            if until_takes_on_air is not None and aired >= until_takes_on_air:
                return
        self._finalize_unfinished()

    def _finalize_unfinished(self) -> None:
        for row in self.log:
            if row.get("clip") is None and row.get("t_ready") is None and row.get("status") == "ready":
                row["status"] = "skipped_end"

    def write_log(self, path: Path | None = None) -> Path:
        self._finalize_unfinished()
        path = Path(path or self.base_dir / "out" / "takes.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in self.log))
        return path
