"""E3 — Voice effect masking (TDD §7).

Runs E2's raw takes through the §6 robot filtergraph and drops them next to
the raw versions for the same blind listen. Pass: treated takes rated >=
raw takes for consistency.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from post import apply_voice_effect  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent / "e1_e2_e3_takes" / "ready"
TREATED_DIR = Path(__file__).resolve().parent / "e1_e2_e3_takes" / "treated"


async def main() -> None:
    clips = sorted(RAW_DIR.glob("*.mp4"))
    if not clips:
        raise SystemExit(f"no clips found in {RAW_DIR} — run e1_verbatim.py first")

    TREATED_DIR.mkdir(parents=True, exist_ok=True)
    for clip in clips:
        out = TREATED_DIR / clip.name
        await apply_voice_effect(clip, out)
        print(f"treated {out}")

    print(
        f"\n{len(clips)} treated takes in {TREATED_DIR}. Blind-listen against "
        f"{RAW_DIR} and compare consistency ratings."
    )


if __name__ == "__main__":
    asyncio.run(main())
