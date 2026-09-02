"""Write three tweet discussions before any cook. Fake writer only."""

from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from runtime_flight.config import load_config, validate_config
from runtime_flight.fal_gateway import H3_MAX_TURBO_ENDPOINT
from runtime_flight.models import Thought
from runtime_flight.prepare_pass import apply_prepare_overrides
from runtime_flight.prepare_queue import run_prepare_queue
from runtime_flight.source import STAGED_BINDING
from test_prepare_pass import BarrierPerformer
from test_preflight import _complete_env, _make_flight_setup, _write_flight_config

FORBIDDEN = {
    "harness_live",
    "obs_session",
    "playhead",
    "run_live",
    "studio",
}


@pytest.fixture
def flight_setup(tmp_path: Path) -> dict:
    return _make_flight_setup(tmp_path / "pack-root")


class ScriptWriter:
    def __init__(self, client) -> None:
        del client
        self.calls: list[str] = []

    async def write_point(self, package, planned, next_speaker, *args, **kwargs):
        del args, kwargs
        self.calls.append(package.item_id)
        index = len(planned)
        speaker = next_speaker
        return (
            Thought(
                speaker=speaker,
                text=f"{package.item_id} turn {index + 1}",
                thought_open=False,
                angle_used="unlock",
            ),
        )


def _write_staged(root: Path, tweet_id: str, author: str) -> Path:
    dest = root / tweet_id
    dest.mkdir(parents=True)
    text = f"Public note {tweet_id} about a workflow."
    url = f"https://x.com/{author}/status/{tweet_id}"
    excerpt = dest / "excerpt.txt"
    excerpt.write_text(text + "\n", encoding="utf-8")
    packet = {
        "tweet": {
            "id": tweet_id,
            "author": author,
            "text": text,
            "url": url,
        },
        "linked_source": {
            "title": f"Note {tweet_id}",
            "subtitle": "A public workflow note",
            "url": "https://example.com/note",
            "excerpt_path": "excerpt.txt",
        },
        "reviewed": True,
    }
    (dest / "source_packet.local.json").write_text(
        json.dumps(packet, indent=2) + "\n", encoding="utf-8"
    )
    lock = {
        "binding": STAGED_BINDING,
        "tweet_id": tweet_id,
        "tweet_author": author,
        "tweet_url": url,
        "source_packet_sha256": hashlib.sha256(
            json.dumps(packet, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest(),
        "tweet_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "excerpt_sha256": hashlib.sha256(excerpt.read_bytes()).hexdigest(),
        "reviewed_at": "2026-09-02T00:00:00Z",
    }
    (dest / "source_packet.lock.json").write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )
    package = {
        "item_id": tweet_id,
        "question": "What does this workflow unlock?",
        "framing": "A public note about shipping a workflow without a human in the loop.",
        "angles": ["unlock", "catch"],
        "facts": [
            {
                "id": "f1",
                "text": text,
                "source_url": url,
            }
        ],
        "chyron": f"Unlock {tweet_id}",
        "chyron_fact_ids": ["f1"],
        "center": {"author": author, "text": text, "url": url},
        "topic_map": {
            "throughline": "What this workflow unlocks, and the one catch.",
            "debate": "Ship the workflow, then name the catch.",
            "done_when": "We've named the unlock and the catch.",
            "beats": [
                {
                    "id": "beat1",
                    "question": "What does this unlock?",
                    "tension": "The demo is thin, the direction is not.",
                    "bot1_job": "Unpack the capability.",
                    "bot2_job": "Yes-and the next product.",
                    "fact_ids": ["f1"],
                    "done_when": "Unlock and catch are both on the table.",
                }
            ],
        },
    }
    (dest / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    return dest


def test_prepare_queue_writes_all_segments_before_any_cook(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    config = apply_prepare_overrides(
        load_config(config_path),
        endpoint=H3_MAX_TURBO_ENDPOINT,
        duration_s=5,
        rate_768p_usd_per_s=Decimal("0.01"),
    )
    validate_config(config, require_obs=False)
    dirs = [
        _write_staged(tmp_path, "111", "one"),
        _write_staged(tmp_path, "222", "two"),
        _write_staged(tmp_path, "333", "three"),
    ]
    writer = ScriptWriter(None)
    seen: list[BarrierPerformer] = []
    events: list[str] = []

    def writer_factory(client):
        del client
        return writer

    def factory(meter, work_dir, baseline):
        performer = BarrierPerformer(meter, work_dir, baseline, expected=6)
        seen.append(performer)
        events.append("cook")
        return performer

    async def concat_fn(clips, dest: Path) -> None:
        events.append("concat")
        dest.write_bytes(b"concat")

    summary = run_prepare_queue(
        config=config,
        source_dirs=dirs,
        turns=2,
        max_text_requests=6,
        out_dir=tmp_path / "out",
        performer_factory=factory,
        concat_fn=concat_fn,
        writer_factory=writer_factory,
    )
    assert writer.calls == ["111", "111", "222", "222", "333", "333"]
    assert events[0] == "cook"
    assert events.count("concat") == 4
    assert summary["mode"] == "tweet-queue"
    assert [item["tweet_id"] for item in summary["queue"]] == ["111", "222", "333"]
    assert [req.line for req in seen[0].started] == [
        "111 turn 1",
        "111 turn 2",
        "222 turn 1",
        "222 turn 2",
        "333 turn 1",
        "333 turn 2",
    ]


def test_prepare_queue_module_stays_isolated_from_obs() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "prepare_queue.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(FORBIDDEN)
    assert "from runtime_flight.harness_live" not in source
    assert "import fal_client" not in source
