"""E1 — Verbatim delivery (TDD §7).

Generates 8 takes from SCRIPTED_LINES (chained on the hero still, no reset),
so E1/E2/E3/half of E4 can share the same generation run. Pass: >= 7/8
word-accurate when transcribed (local whisper-small, or by ear) and diffed
against the scripted line.

This script does the generation + saves a transcription worksheet; the
actual transcribe-and-diff step is manual (or wire in whisper yourself).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from common import SCRIPTED_LINES, load_config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import Generator, SafetyRejected  # noqa: E402
from post import process_take  # noqa: E402
from run_live import download, upload_hero  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "e1_e2_e3_takes"


async def main() -> None:
    config = load_config()
    video_cfg = config["video"]
    hero_path = Path(config["identity"]["hero_still"])
    if not hero_path.exists():
        raise SystemExit(f"missing {hero_path} — run bake_assets.py first")

    generator = Generator(
        model=video_cfg["model"],
        duration=video_cfg["duration"],
        resolution=video_cfg["resolution"],
        expansion=video_cfg["expansion"],
    )

    anchor_url = await upload_hero(hero_path)
    worksheet = []

    for i, line in enumerate(SCRIPTED_LINES, start=1):
        take_id = f"{i:02d}"
        print(f"[{take_id}] generating: {line!r}")
        try:
            result = await generator.generate(line, anchor_url)
        except SafetyRejected:
            print(f"[{take_id}] DROPPED (422)")
            continue

        raw_path = OUT_DIR / "raw" / f"{take_id}.mp4"
        await download(result.video_url, raw_path)

        frame_path = OUT_DIR / "frames" / f"{take_id}.png"
        ready_path = OUT_DIR / "ready" / f"{take_id}.mp4"
        anchor_url = await process_take(raw_path, frame_path, ready_path, voice_effect=False)

        worksheet.append({"take": take_id, "scripted_line": line, "clip": str(ready_path)})

    worksheet_path = OUT_DIR / "worksheet.json"
    worksheet_path.parent.mkdir(parents=True, exist_ok=True)
    worksheet_path.write_text(json.dumps(worksheet, indent=2))
    print(f"\n{len(worksheet)} takes generated. Transcribe each clip in {OUT_DIR}/ready/")
    print(f"and diff against worksheet.json's scripted_line. Pass: >= 7/8 word-accurate.")


if __name__ == "__main__":
    asyncio.run(main())
