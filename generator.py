"""Generator: submits one line to fal MiniMax H3 Max image-to-video.

HTTP 422 from fal means the safety checker rejected the take — that is a
normal, expected outcome (see spec §5), not a bug to retry blindly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import fal_client

logger = logging.getLogger("deskshow.generator")


class SafetyRejected(Exception):
    """The safety checker rejected this take (HTTP 422). Drop it, don't retry as-is."""


@dataclass
class GenerationResult:
    video_url: str
    inference_s: float
    queue_s: float


class Generator:
    def __init__(
        self,
        model: str = "minimax/h3-max/image-to-video",
        duration: int = 5,
        resolution: str = "768p",
        expansion: str = "balanced",
    ) -> None:
        self._model = model
        self._duration = duration
        self._resolution = resolution
        self._expansion = expansion

    async def generate(self, line: str, image_url: str, persona_direction: str = "") -> GenerationResult:
        prompt = f"{persona_direction} The character says exactly: \"{line}\"".strip()
        submit_t0 = time.monotonic()

        try:
            handle = await fal_client.submit_async(
                self._model,
                arguments={
                    "prompt": prompt,
                    "image_url": image_url,
                    "duration": self._duration,
                    "resolution": self._resolution,
                    "prompt_expansion_mode": self._expansion,
                },
            )
            queue_s = time.monotonic() - submit_t0

            infer_t0 = time.monotonic()
            result = await handle.get()
            inference_s = time.monotonic() - infer_t0
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None) or getattr(
                exc, "status", None
            )
            if status == 422:
                raise SafetyRejected(str(exc)) from exc
            raise

        video_url = result["video"]["url"]
        reported = result.get("timings", {}).get("inference")
        return GenerationResult(
            video_url=video_url,
            inference_s=reported if reported is not None else inference_s,
            queue_s=queue_s,
        )
