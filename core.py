"""Shared plumbing: config load, paths, manifest I/O. (DECISIONS.md D10)"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else REPO_ROOT / "config.yaml"
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    cfg["_root"] = str(cfg_path.resolve().parent)
    return cfg


def out_dirs(root: str | Path) -> dict[str, Path]:
    root = Path(root)
    dirs = {
        "out": root / "out",
        "raw": root / "out" / "raw",
        "ready": root / "out" / "ready",
        "frames": root / "out" / "frames",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


class Manifest:
    """out/takes.jsonl — one JSON object per take. This file IS the measurement
    deliverable (§3): $/min, timing distributions, drift bookkeeping."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, row: dict[str, Any]) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def total_spend(self) -> float:
        return sum(float(r.get("cost_usd", 0.0)) for r in self.rows())

    def next_take_number(self) -> int:
        rows = self.rows()
        return (max((int(r.get("take", 0)) for r in rows), default=0) + 1) if rows else 1


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"{name} is not set. Secrets come from env only — never config or repo.")
    return val
