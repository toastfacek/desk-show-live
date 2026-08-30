"""E2 — Voice drift, raw audio (TDD §7).

Reuses E1's 8 chained takes (run e1_verbatim.py first). Extracts raw audio
from each ready clip into one folder for a blind listen A/B. Pass: a
listener says all 8 are the same character; log a subjective 1-5 drift score.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from post import run_ffmpeg  # noqa: E402

TAKES_DIR = Path(__file__).resolve().parent / "e1_e2_e3_takes" / "ready"
AUDIO_DIR = Path(__file__).resolve().parent / "e1_e2_e3_takes" / "raw_audio"


async def main() -> None:
    clips = sorted(TAKES_DIR.glob("*.mp4"))
    if not clips:
        raise SystemExit(f"no clips found in {TAKES_DIR} — run e1_verbatim.py first")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    for clip in clips:
        out = AUDIO_DIR / f"{clip.stem}.wav"
        await run_ffmpeg("-i", str(clip), "-vn", "-acodec", "pcm_s16le", str(out))
        print(f"extracted {out}")

    print(
        f"\n{len(clips)} raw audio takes in {AUDIO_DIR}. Blind-listen A/B and log a "
        f"1-5 drift score per take (5 = perfectly consistent)."
    )


if __name__ == "__main__":
    asyncio.run(main())
