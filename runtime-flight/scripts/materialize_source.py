"""Task 0 local source files. Never fetches X or the article while on air."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

EXAMPLE_PACKET = Path(__file__).resolve().parents[1] / "inputs" / "source_packet.example.json"
EXAMPLE_EXCERPT = (
    Path(__file__).resolve().parents[1] / "inputs" / "dwarkesh-agent-civilizations.example.txt"
)


def materialize(inputs_dir: Path) -> dict[str, str]:
    inputs_dir = Path(inputs_dir)
    inputs_dir.mkdir(parents=True, exist_ok=True)
    packet = json.loads(EXAMPLE_PACKET.read_text(encoding="utf-8"))
    excerpt_bytes = EXAMPLE_EXCERPT.read_bytes()
    packet_path = inputs_dir / "source_packet.local.json"
    excerpt_path = inputs_dir / packet["linked_source"]["excerpt_path"]
    lock_path = inputs_dir / "source_packet.lock.json"
    packet_path.write_text(
        json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    excerpt_path.write_bytes(excerpt_bytes)
    canonical = json.dumps(
        packet, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    text = packet["tweet"]["text"]
    lock = {
        "source_packet_sha256": hashlib.sha256(canonical).hexdigest(),
        "tweet_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "excerpt_sha256": hashlib.sha256(excerpt_bytes).hexdigest(),
        "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="materialize_source")
    parser.add_argument(
        "--inputs",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "inputs",
    )
    args = parser.parse_args(argv)
    lock = materialize(args.inputs)
    for key, value in lock.items():
        print(f"{key} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
