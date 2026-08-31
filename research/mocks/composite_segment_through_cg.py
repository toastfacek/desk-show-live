#!/usr/bin/env python3
"""Composite the 10.4s H3 segment under the 1080 furniture mock."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOCK = ROOT / "research/mocks/production-view.html"
SEGMENT = ROOT / "out/segment-work/segment-20260831T154227Z/segment.mp4"
WORK = Path("/tmp/cg-composite")
ARTIFACTS = Path("/opt/cursor/artifacts")

TAKE1_S = 5.18
CHROME = [
    "google-chrome",
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--hide-scrollbars",
    "--window-size=1920,1080",
    "--force-device-scale-factor=1",
    "--virtual-time-budget=4000",
]


def shot(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    user = WORK / f"chrome-{dest.stem}"
    user.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            *CHROME,
            f"--user-data-dir={user}",
            f"--screenshot={dest}",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(20):
        if dest.exists() and dest.stat().st_size > 10_000:
            time.sleep(0.4)
            proc.kill()
            proc.wait(timeout=5)
            return
        time.sleep(0.5)
    proc.kill()
    raise SystemExit(f"screenshot failed: {dest}")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if not SEGMENT.exists():
        raise SystemExit(f"missing {SEGMENT}")

    base = MOCK.as_uri()
    shot(f"{base}?demo=1&holes=1&speaker=BOT1", WORK / "furn_bot1.png")
    shot(f"{base}?demo=1&holes=1&speaker=BOT2", WORK / "furn_bot2.png")
    shot(f"{base}?demo=1&speaker=BOT1", WORK / "preview_bot1.png")

    well = (
        "crop=672:768:{x}:0,scale=620:709,crop=620:700:0:4"
    )
    filtergraph = (
        f"[0:v]split=2[Lsrc][Rsrc];"
        f"[Lsrc]{well.format(x=0)}[L];"
        f"[Rsrc]{well.format(x=672)}[R];"
        f"color=c=0x101116:s=1920x1080:r=24:d=10.4[bg];"
        f"[bg][L]overlay=40:100[s1];"
        f"[s1][R]overlay=1260:100[hosts];"
        f"[1:v]format=rgb24,colorkey=0xFF00FF:0.12:0.08[f1];"
        f"[2:v]format=rgb24,colorkey=0xFF00FF:0.12:0.08[f2];"
        f"[hosts][f1]overlay=enable='lt(t,{TAKE1_S})'[h1];"
        f"[h1][f2]overlay=enable='gte(t,{TAKE1_S})'[out]"
    )
    clean = ARTIFACTS / "demo_10s_through_cg_split.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(SEGMENT),
            "-loop",
            "1",
            "-i",
            str(WORK / "furn_bot1.png"),
            "-loop",
            "1",
            "-i",
            str(WORK / "furn_bot2.png"),
            "-filter_complex",
            filtergraph,
            "-map",
            "[out]",
            "-map",
            "0:a?",
            "-t",
            "10.4",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(clean),
        ]
    )

    hud = (
        "drawbox=x=0:y=0:w=1920:h=48:color=0x101116@0.92:t=fill,"
        "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
        "fontsize=22:fontcolor=0xF2F0E8:x=96:y=12:"
        "text='PLAYHEAD %{eif\\:t\\:d}.%{eif\\:mod(t,1)*10\\:d}s   "
        "take1 fal 7.96s   take2 fal 8.72s   "
        "if live\\: take2 late by 3.5s'"
    )
    hud_out = ARTIFACTS / "demo_10s_through_cg_split_latency_hud.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(clean),
            "-vf",
            hud,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(hud_out),
        ]
    )

    for t, name in ((1.2, "demo_split_take1_bot1.png"), (6.4, "demo_split_take2_deb.png")):
        run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(t),
                "-i",
                str(clean),
                "-frames:v",
                "1",
                "-update",
                "1",
                str(ARTIFACTS / name),
            ]
        )

    print(f"wrote {clean}")
    print(f"wrote {hud_out}")


if __name__ == "__main__":
    main()
