"""E4 — Face drift (TDD §7).

Generates two 8-take runs from the same scripted lines: one pure last-frame
chain (no reset), one with anchor_reset_every=5. Builds a contact sheet
(ffmpeg tile of each take's extracted frame) for each run. Pass: the
re-anchored run is visibly closer to the hero still across its contact
sheet; chain drift is documented in the pure-chain sheet.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from common import SCRIPTED_LINES, load_config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import Generator, SafetyRejected  # noqa: E402
from post import extract_last_frame, run_ffmpeg, upload_frame  # noqa: E402
from run_live import download, upload_hero  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent / "e4_takes"


async def run_variant(name: str, reset_every: int, hero_path: Path, hero_url: str, generator: Generator) -> None:
    variant_dir = OUT_DIR / name
    if variant_dir.exists():
        shutil.rmtree(variant_dir)
    frames_dir = variant_dir / "frames"
    frames_dir.mkdir(parents=True)

    anchor_url = hero_url
    for i, line in enumerate(SCRIPTED_LINES, start=1):
        take_id = f"{i:02d}"
        print(f"[{name}/{take_id}] generating: {line!r}")
        try:
            result = await generator.generate(line, anchor_url)
        except SafetyRejected:
            print(f"[{name}/{take_id}] DROPPED (422), skipping")
            continue

        raw_path = variant_dir / "raw" / f"{take_id}.mp4"
        await download(result.video_url, raw_path)

        frame_path = frames_dir / f"{take_id}.png"
        await extract_last_frame(raw_path, frame_path)

        force_hero = reset_every > 0 and i % reset_every == 0
        anchor_url = hero_url if force_hero else await upload_frame(frame_path)

    # Contact sheet: hero still + all 8 frames, 3x3 grid.
    sheet_frames = sorted(frames_dir.glob("*.png"))
    montage_inputs = [str(hero_path)] + [str(p) for p in sheet_frames]
    sheet_path = variant_dir / "contact_sheet.png"
    args = []
    for f in montage_inputs:
        args += ["-i", f]
    n = len(montage_inputs)
    filter_complex = "".join(f"[{i}:v]scale=256:-1[v{i}];" for i in range(n))
    filter_complex += "".join(f"[v{i}]" for i in range(n))
    filter_complex += f"xstack=inputs={n}:layout=" + "|".join(
        f"{(i % 3) * 256}_{(i // 3) * 256}" for i in range(n)
    )
    await run_ffmpeg(*args, "-filter_complex", filter_complex, str(sheet_path))
    print(f"[{name}] contact sheet: {sheet_path}")


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
    hero_url = await upload_hero(hero_path)

    await run_variant("pure_chain", reset_every=0, hero_path=hero_path, hero_url=hero_url, generator=generator)
    await run_variant("reset_every_5", reset_every=5, hero_path=hero_path, hero_url=hero_url, generator=generator)

    print("\nCompare e4_takes/pure_chain/contact_sheet.png vs e4_takes/reset_every_5/contact_sheet.png")


if __name__ == "__main__":
    asyncio.run(main())
