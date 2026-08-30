"""Build the JSON the HTML overlay polls. No OBS. No vendors."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_HOSTS = {
    "host_a": {"name": "PHASEONE[lol]", "handle": "phaseone"},
    "host_b": {"name": "deb", "handle": "deb"},
}

DEFAULT_TICKERS = {
    "sponsors": ["RUNTIME", "DESK SHOW", "REHEARSE", "NO VENDOR IN THIS PACK"],
    "markets": ["VIX 14.2", "NDX 19840", "BTC 64210", "NVDA 118.4"],
}


def load_posts(path: Path) -> dict[str, dict]:
    data = json.loads(Path(path).read_text())
    return {row["id"]: row for row in data.get("posts") or [] if row.get("id")}


def build_state(
    *,
    layout: str,
    headline: str,
    speaking: str | None,
    package: dict | None = None,
    posts: dict[str, dict] | None = None,
    hosts: dict | None = None,
) -> dict:
    package = package or {}
    posts = posts or {}
    item = posts.get(package.get("item_id") or "")
    center = package.get("center") or {"kind": "none"}
    card = {
        "kind": center.get("kind") or "none",
        "author": (item or {}).get("author") or "",
        "text": (item or {}).get("text") or "",
    }
    return {
        "layout": layout,
        "headline": headline,
        "kicker": "NOW",
        "speaking": speaking,
        "show": "RUNTIME",
        "presented_by": "REHEARSE",
        "names": hosts or DEFAULT_HOSTS,
        "center": card,
        "tickers": DEFAULT_TICKERS,
    }


def write_state(path: Path, state: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n")
    return path
