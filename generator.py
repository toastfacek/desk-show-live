"""GENERATOR (§2): fal minimax/h3-max/image-to-video, plus a zero-spend dry-run
generator that renders a local test-card clip (DECISIONS.md D5).

422 = safety-checker rejection → reported as dropped_422, never raised past here.
Anything else: the caller retries once, then holds (§5).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx


@dataclass
class TakeResult:
    ok: bool
    dropped_422: bool = False
    error: str = ""
    raw_path: str = ""          # downloaded mp4 in out/raw/
    t_queue_s: float = 0.0
    t_inference_s: float = 0.0
    t_download_s: float = 0.0
    billed_seconds: float = 0.0
    meta: dict = field(default_factory=dict)


def build_prompt(direction: str, line: str) -> str:
    return f'{direction.strip()} The anchor says exactly: "{line}"'


class FalGenerator:
    def __init__(self, cfg: dict):
        import fal_client  # env FAL_KEY only; import here so dry-run needs no fal_client

        self._fal = fal_client
        v = cfg["video"]
        self.model_id = v["model_id"]
        self.duration = int(v["duration"])
        self.resolution = v["resolution"]
        self.expansion = v.get("expansion", "balanced")
        self.direction = v["direction"]

    async def generate(self, line: str, image_url: str, raw_path: Path) -> TakeResult:
        t_submit = time.monotonic()
        try:
            handle = await self._fal.submit_async(
                self.model_id,
                arguments={
                    "prompt": build_prompt(self.direction, line),
                    "image_url": image_url,
                    "duration": self.duration,
                    "resolution": self.resolution,
                    "prompt_expansion_mode": self.expansion,
                },
            )
            result = await handle.get()
        except Exception as e:  # fal raises on HTTP errors incl. the safety 422
            if _is_422(e):
                return TakeResult(ok=False, dropped_422=True, error=str(e),
                                  billed_seconds=float(self.duration))
            return TakeResult(ok=False, error=str(e))
        t_done = time.monotonic()

        t_inference = float(
            (result.get("timings") or {}).get("inference", 0.0)
        )
        t_queue = max(0.0, (t_done - t_submit) - t_inference)

        video_url = _video_url(result)
        if not video_url:
            return TakeResult(ok=False, error=f"no video url in result: {result}")

        t_dl0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(video_url)
                resp.raise_for_status()
                raw_path.write_bytes(resp.content)
        except Exception as e:
            return TakeResult(ok=False, error=f"download failed: {e}",
                              billed_seconds=float(self.duration))
        t_download = time.monotonic() - t_dl0

        return TakeResult(
            ok=True,
            raw_path=str(raw_path),
            t_queue_s=round(t_queue, 3),
            t_inference_s=round(t_inference, 3),
            t_download_s=round(t_download, 3),
            billed_seconds=float(self.duration),
            meta={"video_url": video_url},
        )


def _is_422(e: Exception) -> bool:
    status = getattr(e, "status_code", None) or getattr(
        getattr(e, "response", None), "status_code", None
    )
    return status == 422 or "422" in str(e)


def _video_url(result: dict) -> str:
    video = result.get("video") or {}
    if isinstance(video, dict) and video.get("url"):
        return video["url"]
    return result.get("video_url", "") or result.get("url", "")


class DryRunGenerator:
    """Renders a 5s test card with the line burned in + a beep track, after a simulated
    queue+denoise latency. Exercises the full loop for $0."""

    def __init__(self, cfg: dict):
        v = cfg["video"]
        self.duration = int(v["duration"])
        self.latency_s = float(cfg.get("dry_run", {}).get("simulate_latency_s", 3.0))

    async def generate(self, line: str, image_url: str, raw_path: Path) -> TakeResult:
        await asyncio.sleep(self.latency_s)
        text = line.replace("\\", "").replace("'", "’").replace(":", "\\:").replace("%", "\\%")
        vf = (
            f"drawtext=text='{text}':fontcolor=white:fontsize=36:"
            "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=12"
        )
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=0x102030:s=1344x768:d={self.duration}:r=24",
            "-f", "lavfi", "-i", f"sine=frequency=280:duration={self.duration}",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(raw_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            return TakeResult(ok=False, error=f"dry-run ffmpeg failed: {err.decode()[-400:]}")
        return TakeResult(
            ok=True,
            raw_path=str(raw_path),
            t_queue_s=0.0,
            t_inference_s=self.latency_s,
            t_download_s=0.0,
            billed_seconds=0.0,  # dry runs are free
        )
