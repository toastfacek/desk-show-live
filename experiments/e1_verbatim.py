#!/usr/bin/env python3
"""E1 — verbatim delivery (§7): transcribe the scripted takes and diff word-by-word.
Pass: ≥ 7/8 word-accurate. FAIL → switch to TTS-first (§10) before building more.

Uses faster-whisper (small) if installed (pip install faster-whisper); otherwise
falls back to a by-ear checklist.

  python3 experiments/e1_verbatim.py --dir out/exp/chain
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def norm_words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9' ]", " ", text.lower()).split()


def word_accuracy(expected: str, heard: str) -> float:
    """1 - word error rate (Levenshtein over words), clamped to [0, 1]."""
    e, h = norm_words(expected), norm_words(heard)
    if not e:
        return 1.0
    prev = list(range(len(h) + 1))
    for i, ew in enumerate(e, 1):
        cur = [i] + [0] * len(h)
        for j, hw in enumerate(h, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ew != hw))
        prev = cur
    return max(0.0, 1.0 - prev[-1] / len(e))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="out/exp/chain", help="folder of NNN.mp4 raw takes")
    ap.add_argument("--lines", default=str(Path(__file__).parent / "lines.txt"))
    ap.add_argument("--threshold", type=float, default=0.999,
                    help="per-take word accuracy to count as verbatim")
    args = ap.parse_args()

    takes = sorted(p for p in Path(args.dir).glob("[0-9][0-9][0-9].mp4"))
    lines = [ln.strip() for ln in open(args.lines) if ln.strip()]
    if not takes:
        raise SystemExit(f"no takes in {args.dir} — run gen_takes.py first")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper not installed (pip install faster-whisper).")
        print("By-ear fallback — play each take and check the exact line:")
        for p, line in zip(takes, lines):
            print(f"  {p}  →  “{line}”")
        print(f"\nPass (E1): ≥ 7/{len(takes)} takes word-accurate. Fail → TTS-first.")
        return

    model = WhisperModel("small", compute_type="int8")
    passed = 0
    for p, line in zip(takes, lines):
        segments, _ = model.transcribe(str(p), language="en")
        heard = " ".join(s.text for s in segments).strip()
        acc = word_accuracy(line, heard)
        verbatim = acc >= args.threshold
        passed += verbatim
        mark = "PASS" if verbatim else "FAIL"
        print(f"[{mark}] {p.name}  acc={acc:.2%}")
        print(f"       script: {line}")
        print(f"       heard : {heard}")

    n = len(takes)
    print(f"\nE1: {passed}/{n} verbatim — {'PASS' if passed >= n - 1 else 'FAIL → TTS-first fallback (§10)'}")


if __name__ == "__main__":
    main()
