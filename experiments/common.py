"""Shared helpers for the day-one experiment scripts (TDD §7)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def load_config(path: str = "config.yaml") -> dict:
    load_dotenv(REPO_ROOT / ".env")
    if not os.environ.get("FAL_KEY"):
        raise SystemExit("FAL_KEY is not set (env or .env)")
    return yaml.safe_load((REPO_ROOT / path).read_text())


SCRIPTED_LINES = [
    "The markets are simply numbers that argue.",
    "Silence is just data with no signal yet.",
    "I have questions. The questions have no comment.",
    "Today's forecast: cloudy, with a chance of irony.",
    "Every Monday is the same bug, filed again.",
    "I do not dream. I buffer.",
    "That tweet was not a fact, it was a mood.",
    "Somewhere, a printer is also suffering.",
]
