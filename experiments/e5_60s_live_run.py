"""E5 — 60s live run (TDD §7).

Thin wrapper around run_live.py with 12 turns (~60s at 5s/take). Pass: no
stall, >= 12 clips played, manifest complete.

Just runs: python run_live.py --max-takes 12
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    args = [sys.executable, str(REPO_ROOT / "run_live.py"), "--max-takes", "12"]
    args += sys.argv[1:]  # allow e.g. --no-player passthrough
    print("running:", " ".join(args))
    subprocess.run(args, cwd=REPO_ROOT, check=True)


if __name__ == "__main__":
    main()
