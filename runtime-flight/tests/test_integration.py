"""Task 15B: zero-cost full integration and AST isolation."""

from __future__ import annotations

import ast
import asyncio
import json
from decimal import Decimal
from pathlib import Path

from obs_harness.player_fake import FakePlayer

from runtime_flight.baseline import BaselineContext
from runtime_flight.evidence import write_evidence_bundle, FlightEvidence
from runtime_flight.harness_live import CLIP_DURATION_S, FakeClock, LiveHarness
from runtime_flight.obs_session import ObsSession
from runtime_flight.source import load_source_packet
from runtime_flight.spend import SpendLedger, SpendMeter
from runtime_flight.verify import verify_bundle
from runtime_flight.writer_pipeline import WriterPipeline
from test_evidence import _fal_requests
from test_harness_live import FakePerformer, LiveWriter, _package
from test_media import write_h3_clip
from test_preflight import _make_flight_setup, _write_source_files
from conftest_obs import complete_obs_client

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}
RUNTIME_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = RUNTIME_ROOT / "runtime_flight"


def _imported_top_level(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    return imported


def test_runtime_flight_does_not_import_root_scaffold() -> None:
    scanned = 0
    for path in PACKAGE_ROOT.rglob("*.py"):
        imported = _imported_top_level(path)
        assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES), path
        scanned += 1
    assert scanned > 10


def test_zero_cost_flight_writes_verifiable_evidence(tmp_path: Path) -> None:
    setup = _make_flight_setup(tmp_path / "pack-root")
    sources = _write_source_files(tmp_path / "inputs")
    source = load_source_packet(sources["packet"], sources["lock"])
    baseline = BaselineContext.load(setup["data_dir"], setup["locked"].id)

    recording = tmp_path / "programme.mp4"
    write_h3_clip(recording, duration_s=90.0, width=640, height=360, fps=5, color="0x336699")

    clock = FakeClock()
    player = FakePlayer()
    player.set_clip_duration(CLIP_DURATION_S)
    meter = SpendMeter(
        cap_usd=Decimal("12.00"),
        rate_768p_usd_per_s=Decimal("0.08"),
        duration_s=5,
        mode="live",
        ledger=SpendLedger(tmp_path / "reservations.jsonl"),
    )
    performer = FakePerformer(clock, meter, tmp_path, delay_s=0.0)
    client = complete_obs_client()
    client.record_duration_ms = 90_000
    session = ObsSession(client=client, poll_interval_s=0.0)
    harness = LiveHarness(
        clock=clock,
        player=player,
        pipeline=WriterPipeline(LiveWriter()),
        performer=performer,
        meter=meter,
        baseline=baseline,
        package=_package(),
        target_duration_s=90.0,
        obs_session=session,
    )

    async def run() -> None:
        await harness.run_with_obs(max_t=90.0)

    asyncio.run(run())
    assert harness.aired_count >= 10
    speakers = {
        row["speaker"]
        for row in harness.log
        if row.get("t_on_air") is not None and row.get("speaker")
    }
    assert speakers >= {"BOT1", "BOT2"}
    assert performer.max_inflight == 1
    assert not any(call[0] == "stop_stream" for call in client.calls)
    assert ("stop_record",) in client.calls

    lock = json.loads(sources["lock"].read_text(encoding="utf-8"))
    evidence = FlightEvidence(
        flight_id="zero-cost",
        baseline_id=baseline.baseline_id,
        mode="live",
        target_duration_s=90,
        stop_reason=harness.stop_reason,
        baseline_manifest_path=setup["locked"].manifest_path,
        source_packet_path=sources["packet"],
        source_lock_path=sources["lock"],
        excerpt_path=sources["excerpt"],
        package=harness.package,
        takes=harness.log,
        events=harness.events,
        fal_requests=_fal_requests(
            [
                {
                    **row,
                    "prompt": next(
                        (req.prompt for req in performer.started if req.take == row["take"]),
                        row.get("prompt") or "Active host voice: test",
                    ),
                    "request_id": row.get("request_id") or f"req-{row['take']}",
                }
                for row in harness.log
            ]
        ),
        recording_path=recording,
        recording_duration_s=90.0,
        reserved_cost_upper_bound_usd=meter.total,
        spend_rate_768p_usd_per_s=Decimal("0.08"),
        spend_duration_s=5,
        reservations=[
            {
                "id": row.id,
                "take": row.take,
                "attempt": row.attempt,
                "reserved_cost_usd": str(row.reserved_cost_usd),
                "calculation": f"{meter.rate_768p_usd_per_s} * {meter.duration_s}",
            }
            for row in meter.ledger.records()
        ],
        source_hashes={
            "source_packet_sha256": lock["source_packet_sha256"],
            "tweet_text_sha256": lock["tweet_text_sha256"],
            "excerpt_sha256": lock["excerpt_sha256"],
        },
        beats=harness.beats,
        spend_cap_usd=Decimal("12.00"),
        text_requests=0,
        text_request_limit=24,
        t_end=harness.t,
        secrets=(),
    )
    del source
    bundle = write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)
    result = verify_bundle(bundle, mode="automated", secrets=())
    assert result.ok, result.failures
    assert result.verdict is None
    flight = json.loads((bundle / "flight.json").read_text(encoding="utf-8"))
    assert flight["baseline_id"] == baseline.baseline_id
    assert Decimal(flight["reserved_cost_upper_bound_usd"]) <= Decimal("12.00")
