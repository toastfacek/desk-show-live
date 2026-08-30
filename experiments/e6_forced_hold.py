"""E6 — Forced hold (TDD §7).

Simulates one in-flight generation dying mid-run by monkeypatching
Generator.generate to fail on take #3, then runs the generation loop
(no playhead needed — mpv's --keep-open is what actually renders the
freeze in production; here we check the loop itself doesn't stall).
Pass: the failed take is skipped, the loop keeps going, and later takes
still reach "ready" in the manifest without operator action.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from common import load_config

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generator as generator_module  # noqa: E402
from run_live import generation_loop, upload_hero  # noqa: E402
from writer import Writer  # noqa: E402

KILL_ON_TAKE = 3


async def main() -> None:
    config = load_config()
    config["paths"]["manifest"] = "experiments/e6_takes/takes.jsonl"
    config["paths"]["raw_dir"] = "experiments/e6_takes/raw"
    config["paths"]["ready_dir"] = "experiments/e6_takes/ready"
    config["paths"]["frames_dir"] = "experiments/e6_takes/frames"

    hero_path = Path(config["identity"]["hero_still"])
    if not hero_path.exists():
        raise SystemExit(f"missing {hero_path} — run bake_assets.py first")
    hero_url = await upload_hero(hero_path)

    writer_cfg = config["writer"]
    writer = Writer(
        base_url=writer_cfg["base_url"],
        model=writer_cfg["model"],
        api_key="",
        persona=config["persona"],
        topics=config["topics"],
        max_words=writer_cfg["max_words"],
        canned_fallback=writer_cfg.get("canned_fallback"),
    )

    real_generate = generator_module.Generator.generate
    call_count = {"n": 0}

    async def flaky_generate(self, line, image_url, persona_direction=""):
        call_count["n"] += 1
        if call_count["n"] == KILL_ON_TAKE:
            raise RuntimeError("simulated killed in-flight generation")
        return await real_generate(self, line, image_url, persona_direction)

    generator_module.Generator.generate = flaky_generate
    try:
        generator = generator_module.Generator(
            model=config["video"]["model"],
            duration=config["video"]["duration"],
            resolution=config["video"]["resolution"],
            expansion=config["video"]["expansion"],
        )
        ready_queue: asyncio.Queue = asyncio.Queue(maxsize=1)

        async def drain(q: asyncio.Queue) -> None:
            while True:
                item = await q.get()
                if item is None:
                    break

        await asyncio.gather(
            generation_loop(config, writer, generator, ready_queue, hero_url, max_takes=6),
            drain(ready_queue),
        )
    finally:
        generator_module.Generator.generate = real_generate

    print(f"\nSimulated kill on take {KILL_ON_TAKE}. Check "
          f"{config['paths']['manifest']} — later takes should still show status=ready.")


if __name__ == "__main__":
    asyncio.run(main())
