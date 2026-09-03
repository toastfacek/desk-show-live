"""Infinite list orchestrator. Fake planner, writer, performer. No OBS."""

from __future__ import annotations

import ast
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from runtime_flight.__main__ import main
from runtime_flight.config import load_config, validate_config
from runtime_flight.content_queue import CLAIMED, PENDING, pending_ids
from runtime_flight.fal_gateway import H3_MAX_TURBO_ENDPOINT
from runtime_flight.list_load import load_list
from runtime_flight.models import Fact, SegmentPackage, TweetCard
from runtime_flight.orchestrator import run_orchestrator
from runtime_flight.prepare_pass import apply_prepare_overrides
from test_preflight import _complete_env, _make_flight_setup, _write_flight_config
from test_prepare_queue import ScriptWriter
from test_queue_worker import InstantPerformer

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


class ScriptPlanner:
    async def plan(self, source, baseline, time_budget_s=None, voices=None):
        del baseline, time_budget_s, voices
        return SegmentPackage(
            item_id=source.tweet.id,
            question="What does this unlock?",
            framing="A public note about shipping a workflow.",
            angles=("unlock", "catch"),
            facts=(
                Fact(
                    id="f1",
                    text=source.tweet.text,
                    source_url=source.tweet.url,
                ),
            ),
            chyron=f"Unlock {source.tweet.id}",
            chyron_fact_ids=("f1",),
            center=TweetCard(
                author=source.tweet.author,
                text=source.tweet.text,
                url=source.tweet.url,
            ),
        )


def _config(tmp_path: Path, flight_setup: dict, monkeypatch: pytest.MonkeyPatch):
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
    return config


def _list_and_fixtures(tmp_path: Path, tweet_ids: tuple[str, ...]) -> tuple[Path, dict]:
    tweets = []
    fixtures = {}
    for tweet_id in tweet_ids:
        author = f"user{tweet_id}"
        url = f"https://x.com/{author}/status/{tweet_id}"
        text = f"Public note {tweet_id} about a workflow."
        tweets.append({"url": url})
        fixtures[url] = {
            "id": tweet_id,
            "author": author,
            "text": text,
            "url": url,
        }
    path = tmp_path / "list.json"
    path.write_text(json.dumps({"list_id": "99", "tweets": tweets}) + "\n", encoding="utf-8")
    return path, fixtures


def test_run_list_comments_in_list_order_then_stops_empty(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, flight_setup, monkeypatch)
    inbox = tmp_path / "inbox"
    list_file, fixtures = _list_and_fixtures(tmp_path, ("333", "111", "222"))
    events: list[str] = []

    def factory(meter, work_dir, baseline):
        return InstantPerformer(meter, work_dir, baseline, events=events)

    async def concat_fn(clips, dest: Path) -> None:
        dest.write_bytes(b"concat")

    summary = run_orchestrator(
        config=config,
        inbox=inbox,
        until="2099-01-01T00:00:00Z",
        turns=2,
        max_text_requests=12,
        out_dir=tmp_path / "out",
        list_file=list_file,
        fixtures=fixtures,
        performer_factory=factory,
        concat_fn=concat_fn,
        writer_factory=lambda client: ScriptWriter(client),
        planner_factory=lambda client: ScriptPlanner(),
    )
    assert summary["mode"] == "run-list"
    assert summary["stop_reason"] == "empty"
    assert summary["commented"] == ["333", "111", "222"]
    assert pending_ids(inbox) == ()
    assert summary["ready_s"] == 30
    cooks = [item for item in events if item.startswith("cook:")]
    assert cooks == ["cook:1", "cook:2", "cook:3", "cook:4", "cook:5", "cook:6"]


def test_run_list_stops_when_spend_runway_is_gone(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = replace(_config(tmp_path, flight_setup, monkeypatch), spend_cap_usd=Decimal("0.10"))
    inbox = tmp_path / "inbox"
    list_file, fixtures = _list_and_fixtures(tmp_path, ("333", "111", "222"))

    async def concat_fn(clips, dest: Path) -> None:
        dest.write_bytes(b"concat")

    summary = run_orchestrator(
        config=config,
        inbox=inbox,
        turns=2,
        max_text_requests=12,
        out_dir=tmp_path / "out",
        list_file=list_file,
        fixtures=fixtures,
        performer_factory=lambda meter, work_dir, baseline: InstantPerformer(
            meter, work_dir, baseline
        ),
        concat_fn=concat_fn,
        writer_factory=lambda client: ScriptWriter(client),
        planner_factory=lambda client: ScriptPlanner(),
    )
    assert summary["stop_reason"] == "runway"
    assert summary["commented"] == ["333"]
    assert pending_ids(inbox) == ("111", "222")


def test_load_list_file_leaves_items_for_the_producer(
    tmp_path: Path,
) -> None:
    inbox = tmp_path / "inbox"
    list_file, fixtures = _list_and_fixtures(tmp_path, ("333", "111"))
    payload = load_list(inbox, list_file=list_file, fixtures=fixtures)
    assert payload["enqueued"] == ["333", "111"]
    assert pending_ids(inbox) == ("333", "111")
    assert not (inbox / "pending" / "333" / "package.json").is_file()


def test_run_list_drops_invalid_source_and_continues(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, flight_setup, monkeypatch)
    inbox = tmp_path / "inbox"
    list_file, fixtures = _list_and_fixtures(tmp_path, ("333", "111"))
    load_list(inbox, list_file=list_file, fixtures=fixtures)
    packet_path = inbox / PENDING / "333" / "source_packet.local.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["tweet"]["text"] = "x" * 2001
    packet_path.write_text(json.dumps(packet) + "\n", encoding="utf-8")

    async def concat_fn(clips, dest: Path) -> None:
        dest.write_bytes(b"concat")

    summary = run_orchestrator(
        config=config,
        inbox=inbox,
        turns=2,
        max_text_requests=12,
        out_dir=tmp_path / "out",
        performer_factory=lambda meter, work_dir, baseline: InstantPerformer(
            meter, work_dir, baseline
        ),
        concat_fn=concat_fn,
        writer_factory=lambda client: ScriptWriter(client),
        planner_factory=lambda client: ScriptPlanner(),
    )
    assert summary["stop_reason"] == "empty"
    assert summary["commented"] == ["111"]
    assert summary["dropped"][0]["tweet_id"] == "333"
    assert pending_ids(inbox) == ()


def test_run_list_retries_leftover_claimed(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, flight_setup, monkeypatch)
    inbox = tmp_path / "inbox"
    list_file, fixtures = _list_and_fixtures(tmp_path, ("333", "111"))
    load_list(inbox, list_file=list_file, fixtures=fixtures)
    claimed = inbox / CLAIMED / "333"
    (inbox / PENDING / "333").rename(claimed)

    async def concat_fn(clips, dest: Path) -> None:
        dest.write_bytes(b"concat")

    summary = run_orchestrator(
        config=config,
        inbox=inbox,
        turns=2,
        max_text_requests=12,
        out_dir=tmp_path / "out",
        performer_factory=lambda meter, work_dir, baseline: InstantPerformer(
            meter, work_dir, baseline
        ),
        concat_fn=concat_fn,
        writer_factory=lambda client: ScriptWriter(client),
        planner_factory=lambda client: ScriptPlanner(),
    )
    assert summary["stop_reason"] == "empty"
    assert summary["commented"] == ["333", "111"]
    assert not claimed.exists()
    assert pending_ids(inbox) == ()


def test_run_list_passes_selected_chat_to_writer(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(tmp_path, flight_setup, monkeypatch)
    inbox = tmp_path / "inbox"
    list_file, fixtures = _list_and_fixtures(tmp_path, ("333",))
    chat_path = tmp_path / "chat.json"
    chat_path.write_text(
        json.dumps(
            {
                "comments": [
                    {"id": "c1", "author": "sam", "text": "Who actually posted this?"},
                    {"id": "c2", "author": "lee", "text": "lol"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    writer = ScriptWriter(None)

    class ChatTextClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def complete_json(self, *, system, user):
            del system, user
            return {"picks": [{"comment_id": "c1", "why": "asks who wrote it"}]}

    monkeypatch.setattr("runtime_flight.orchestrator.TextClient", ChatTextClient)

    async def concat_fn(clips, dest: Path) -> None:
        dest.write_bytes(b"concat")

    summary = run_orchestrator(
        config=config,
        inbox=inbox,
        turns=2,
        max_text_requests=12,
        out_dir=tmp_path / "out",
        list_file=list_file,
        fixtures=fixtures,
        chat_file=chat_path,
        performer_factory=lambda meter, work_dir, baseline: InstantPerformer(
            meter, work_dir, baseline
        ),
        concat_fn=concat_fn,
        writer_factory=lambda client: writer,
        planner_factory=lambda client: ScriptPlanner(),
    )
    assert summary["commented"] == ["333"]
    assert writer.chats
    assert writer.chats[0] == (
        {"text": "Who actually posted this?", "why": "asks who wrote it"},
    )


def test_run_list_cli_refuses_without_paid_flag(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.delenv("RUNTIME_ALLOW_PAID", raising=False)
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "run-list",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--inbox",
            str(tmp_path / "inbox"),
            "--confirm-text-requests",
            "24",
        ],
        run_list_runner=lambda **kwargs: {"ok": True},
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "paid flag absent" in captured.err


def test_orchestrator_stays_isolated_from_obs() -> None:
    path = Path(__file__).resolve().parents[1] / "runtime_flight" / "orchestrator.py"
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
    assert "from runtime_flight.obs_session" not in source
    assert "import fal_client" not in source
