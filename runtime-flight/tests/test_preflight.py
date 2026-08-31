"""Task 5B: external preflight probes. No live OBS or paid fal calls."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from pack_manager.assets import AssetStore
from pack_manager.baselines import BaselineService
from pack_manager.candidates import CandidateService
from pack_manager.db import Database
from pack_manager.packs import PackService
from runtime_flight.__main__ import main
from runtime_flight.config import load_config, validate_config
from runtime_flight.obs_session import ObsSession
from runtime_flight.preflight import (
    TEXT_PROBE_MESSAGES,
    PreflightError,
    run_preflight,
    submit_fal_job,
)
from test_baseline import make_png_bytes
from test_config import (
    SECRET_API_KEY,
    SECRET_BASE_URL,
    SECRET_OBS_PASSWORD,
    _minimal_config,
    _set_complete_env,
    _write_config,
)
from conftest import character_manifest_v2, scene_manifest_v2
from conftest_obs import FakeObsClient, complete_obs_client

FORBIDDEN_ROOT_MODULES = {
    "writer",
    "post",
    "spend",
    "generator",
    "playhead",
    "run_live",
    "studio",
}

TWEET_TEXT = "Hello café\nworld"
EXCERPT_TEXT = "Reviewed excerpt body.\n"
PACKET_NAME = "source_packet.local.json"
LOCK_NAME = "source_packet.lock.json"
EXCERPT_NAME = "dwarkesh-agent-civilizations.txt"


def _canonical_packet_digest(packet: dict) -> str:
    canonical = json.dumps(
        packet,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _packet_payload() -> dict:
    return {
        "tweet": {
            "id": "2093833419377815719",
            "author": "dwarkesh_sp",
            "text": TWEET_TEXT,
            "url": "https://x.com/dwarkesh_sp/status/2093833419377815719",
        },
        "linked_source": {
            "title": "The Rise and Fall of Agent Civilizations",
            "subtitle": "The whole OpenAI/Hugging Face story in plain English",
            "url": "https://www.dwarkesh.com/p/openai-huggingface",
            "excerpt_path": EXCERPT_NAME,
        },
        "reviewed": True,
    }


def _write_source_files(inputs_dir: Path, *, packet: dict | None = None) -> dict:
    inputs_dir.mkdir(parents=True, exist_ok=True)
    payload = packet if packet is not None else _packet_payload()
    packet_path = inputs_dir / PACKET_NAME
    excerpt_path = inputs_dir / EXCERPT_NAME
    lock_path = inputs_dir / LOCK_NAME
    packet_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    excerpt_path.write_text(EXCERPT_TEXT, encoding="utf-8")
    lock = {
        "source_packet_sha256": _canonical_packet_digest(payload),
        "tweet_text_sha256": hashlib.sha256(TWEET_TEXT.encode("utf-8")).hexdigest(),
        "excerpt_sha256": hashlib.sha256(excerpt_path.read_bytes()).hexdigest(),
        "reviewed_at": "2026-08-31T00:00:00+00:00",
    }
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return {"packet": packet_path, "lock": lock_path, "excerpt": excerpt_path, "lock_data": lock}


def _write_flight_config(
    tmp_path: Path,
    flight_setup: dict,
    *,
    source_dir: Path | None = None,
) -> Path:
    inputs = source_dir if source_dir is not None else (tmp_path / "inputs")
    if not (inputs / PACKET_NAME).is_file():
        _write_source_files(inputs)
    payload = _minimal_config()
    payload["pack_manager_data_dir"] = str(flight_setup["data_dir"])
    payload["source_packet"] = str((inputs / PACKET_NAME).resolve())
    payload["source_lock"] = str((inputs / LOCK_NAME).resolve())
    return _write_config(tmp_path, payload)


def _complete_env(monkeypatch: pytest.MonkeyPatch, flight_setup: dict) -> None:
    _set_complete_env(monkeypatch)
    monkeypatch.setenv("RUNTIME_BASELINE_ID", flight_setup["locked"].id)
    monkeypatch.setenv("FAL_KEY", "fal-test-key-not-for-submission")


def _make_flight_setup(tmp_path: Path) -> dict:
    data_dir = tmp_path / "pack-data"
    database = Database(data_dir / "manager.sqlite3")
    database.initialize()
    asset_store = AssetStore(data_dir, database)
    pack_service = PackService(database, asset_store)
    candidate_service = CandidateService(database, asset_store, pack_service)
    baseline_service = BaselineService(
        database, asset_store, pack_service, candidate_service
    )

    bot1_asset = asset_store.put_bytes("bot1.png", make_png_bytes(64, 64), "image/png")
    bot2_asset = asset_store.put_bytes("bot2.png", make_png_bytes(64, 64), "image/png")
    scene_asset = asset_store.put_bytes("studio.png", make_png_bytes(64, 64), "image/png")
    hero = asset_store.put_bytes("hero.png", make_png_bytes(), "image/png")

    bot1 = pack_service.create_pack("character", "BOT1")
    bot2 = pack_service.create_pack("character", "BOT2")
    scene = pack_service.create_pack("scene", "Studio")
    bot1_version = pack_service.create_version(
        bot1.id, character_manifest_v2([bot1_asset.id])
    )
    bot2_version = pack_service.create_version(
        bot2.id, character_manifest_v2([bot2_asset.id])
    )
    scene_version = pack_service.create_version(
        scene.id, scene_manifest_v2([scene_asset.id])
    )
    candidate = candidate_service.create(
        character_versions={
            "BOT1": (bot1_version.pack_id, bot1_version.version),
            "BOT2": (bot2_version.pack_id, bot2_version.version),
        },
        scene_pack_id=scene_version.pack_id,
        scene_version=scene_version.version,
        hero_asset_id=hero.id,
    )
    approved = candidate_service.approve(
        candidate.id, canonical=True, review_note="flight-ready"
    )
    locked = baseline_service.lock_run(approved.cast_key)
    return {
        "data_dir": data_dir,
        "baseline_service": baseline_service,
        "locked": locked,
    }


@pytest.fixture
def flight_setup(tmp_path: Path) -> dict:
    return _make_flight_setup(tmp_path / "pack-root")


@pytest.fixture
def ready_config(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    config = load_config(config_path)
    validate_config(config)
    return config


def _session(client: FakeObsClient | None = None) -> ObsSession:
    return ObsSession(client=client or complete_obs_client())


def _fal_spy(monkeypatch: pytest.MonkeyPatch) -> list:
    calls: list = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("fal submission helper was reached")

    monkeypatch.setattr("runtime_flight.preflight.submit_fal_job", _spy)
    return calls


def _pong_response(url, *, headers, json, timeout):
    return {
        "provider": "test-provider",
        "model": json["model"],
        "choices": [{"message": {"role": "assistant", "content": "pong"}}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
    }


def test_baseline_probe_fails_for_unknown_id(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    broken = replace(ready_config, baseline_id="does-not-exist")
    with pytest.raises(PreflightError, match="baseline"):
        run_preflight(broken, session=_session())
    assert fal_calls == []


def test_source_packet_rejects_path_escape(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _complete_env(monkeypatch, flight_setup)
    fal_calls = _fal_spy(monkeypatch)
    inputs = tmp_path / "inputs"
    packet = _packet_payload()
    packet["linked_source"]["excerpt_path"] = "../outside.txt"
    (tmp_path / "outside.txt").write_text("escaped", encoding="utf-8")
    _write_source_files(inputs, packet=packet)
    config = load_config(_write_flight_config(tmp_path, flight_setup, source_dir=inputs))
    with pytest.raises(PreflightError, match="escape|excerpt"):
        run_preflight(config, session=_session())
    assert fal_calls == []


def test_source_packet_rejects_symlink(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _complete_env(monkeypatch, flight_setup)
    fal_calls = _fal_spy(monkeypatch)
    inputs = tmp_path / "inputs"
    written = _write_source_files(inputs)
    link = inputs / "linked_packet.json"
    link.symlink_to(written["packet"])
    config_path = _write_flight_config(tmp_path, flight_setup, source_dir=inputs)
    config = replace(load_config(config_path), source_packet=link)
    with pytest.raises(PreflightError, match="symlink"):
        run_preflight(config, session=_session())
    assert fal_calls == []


def test_source_packet_rejects_invalid_utf8(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _complete_env(monkeypatch, flight_setup)
    fal_calls = _fal_spy(monkeypatch)
    inputs = tmp_path / "inputs"
    _write_source_files(inputs)
    (inputs / PACKET_NAME).write_bytes(b'{"reviewed": true, "tweet": "\xff"}')
    config = load_config(_write_flight_config(tmp_path, flight_setup, source_dir=inputs))
    with pytest.raises(PreflightError, match="UTF-8"):
        run_preflight(config, session=_session())
    assert fal_calls == []


def test_source_packet_rejects_oversized_file(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _complete_env(monkeypatch, flight_setup)
    fal_calls = _fal_spy(monkeypatch)
    inputs = tmp_path / "inputs"
    _write_source_files(inputs)
    (inputs / EXCERPT_NAME).write_bytes(b"x" * (1024 * 1024 + 1))
    config = load_config(_write_flight_config(tmp_path, flight_setup, source_dir=inputs))
    with pytest.raises(PreflightError, match="1 MiB|oversized"):
        run_preflight(config, session=_session())
    assert fal_calls == []


@pytest.mark.parametrize("field", ["source_packet_sha256", "tweet_text_sha256", "excerpt_sha256"])
def test_source_lock_rejects_hash_mismatch(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
):
    _complete_env(monkeypatch, flight_setup)
    fal_calls = _fal_spy(monkeypatch)
    inputs = tmp_path / "inputs"
    written = _write_source_files(inputs)
    lock = written["lock_data"]
    lock[field] = "0" * 64
    written["lock"].write_text(json.dumps(lock), encoding="utf-8")
    config = load_config(_write_flight_config(tmp_path, flight_setup, source_dir=inputs))
    with pytest.raises(PreflightError, match="mismatch"):
        run_preflight(config, session=_session())
    assert fal_calls == []


def test_source_packet_rejects_unreviewed(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _complete_env(monkeypatch, flight_setup)
    fal_calls = _fal_spy(monkeypatch)
    inputs = tmp_path / "inputs"
    packet = _packet_payload()
    packet["reviewed"] = False
    _write_source_files(inputs, packet=packet)
    config = load_config(_write_flight_config(tmp_path, flight_setup, source_dir=inputs))
    with pytest.raises(PreflightError, match="reviewed"):
        run_preflight(config, session=_session())
    assert fal_calls == []


def test_source_packet_rejects_empty_regular_file(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    _complete_env(monkeypatch, flight_setup)
    fal_calls = _fal_spy(monkeypatch)
    inputs = tmp_path / "inputs"
    _write_source_files(inputs)
    (inputs / LOCK_NAME).write_bytes(b"")
    config = load_config(_write_flight_config(tmp_path, flight_setup, source_dir=inputs))
    with pytest.raises(PreflightError, match="empty"):
        run_preflight(config, session=_session())
    assert fal_calls == []


def test_ffmpeg_and_ffprobe_probe_fails_when_missing(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    monkeypatch.setattr("runtime_flight.preflight.shutil.which", lambda name: None)
    with pytest.raises(PreflightError, match="ffmpeg|ffprobe"):
        run_preflight(ready_config, session=_session())
    assert fal_calls == []


def test_obs_contract_probe_fails(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    with pytest.raises(PreflightError, match="contract|scene|input"):
        run_preflight(ready_config, session=ObsSession(client=FakeObsClient()))
    assert fal_calls == []


def test_obs_streaming_probe_fails_and_does_not_stop_stream(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    client = complete_obs_client()
    client.streaming = True
    stop_calls: list = []

    def stop_stream():
        stop_calls.append(("stop_stream",))
        client.calls.append(("stop_stream",))
        client.streaming = False

    client.stop_stream = stop_stream  # type: ignore[attr-defined]
    with pytest.raises(PreflightError, match="streaming"):
        run_preflight(ready_config, session=ObsSession(client=client))
    assert client.streaming is True
    assert stop_calls == []
    assert fal_calls == []


def test_recording_configured_probe_fails_when_obs_record_false(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    broken = replace(ready_config, obs_record=False)
    with pytest.raises(PreflightError, match="record"):
        run_preflight(broken, session=_session())
    assert fal_calls == []


def test_recording_configured_probe_fails_when_status_unreadable(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    client = complete_obs_client()

    def boom():
        raise RuntimeError("record status unavailable")

    client.get_record_status = boom  # type: ignore[method-assign]
    with pytest.raises(PreflightError, match="record"):
        run_preflight(ready_config, session=ObsSession(client=client))
    assert fal_calls == []
    assert ("start_record",) not in client.calls


def test_recording_configured_probe_fails_when_already_recording(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    client = complete_obs_client()
    client.recording = True
    with pytest.raises(PreflightError, match="record"):
        run_preflight(ready_config, session=ObsSession(client=client))
    assert fal_calls == []
    assert ("start_record",) not in client.calls
    assert ("stop_record",) not in client.calls
    assert client.recording is True


def test_text_configuration_probe_fails_when_missing(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    broken = replace(ready_config, text_api_key=None)
    with pytest.raises(PreflightError, match="TEXT_API_KEY|text"):
        run_preflight(broken, session=_session())
    assert fal_calls == []


def test_fal_key_probe_fails_when_missing(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(PreflightError, match="FAL_KEY"):
        run_preflight(ready_config, session=_session())
    assert fal_calls == []


def test_failed_earlier_probe_never_reaches_fal_submission(ready_config, monkeypatch):
    fal_calls = _fal_spy(monkeypatch)
    monkeypatch.delenv("FAL_KEY", raising=False)
    broken = replace(ready_config, baseline_id="missing-baseline")
    with pytest.raises(PreflightError, match="baseline"):
        run_preflight(broken, session=_session())
    assert fal_calls == []
    with pytest.raises(RuntimeError, match="must not submit"):
        submit_fal_job("minimax/h3-max/image-to-video", {})


def test_default_preflight_skips_text_http(ready_config, monkeypatch):
    http_calls: list = []

    def forbidden(*args, **kwargs):
        http_calls.append((args, kwargs))
        raise AssertionError("text HTTP must not run by default")

    result = run_preflight(
        ready_config,
        session=_session(),
        http_post=forbidden,
    )
    assert http_calls == []
    assert result.text_probe is None
    assert result.spend_cap_usd == Decimal("12.00")
    assert result.fal_key_present is True


@pytest.mark.parametrize("confirm", [0, 2])
def test_probe_text_without_confirm_fails_before_http(ready_config, confirm):
    http_calls: list = []

    def forbidden(*args, **kwargs):
        http_calls.append(1)
        raise AssertionError("text HTTP requires confirm-text-requests 1")

    with pytest.raises(PreflightError, match="confirm-text-requests"):
        run_preflight(
            ready_config,
            session=_session(),
            probe_text=True,
            confirm_text_requests=confirm,
            http_post=forbidden,
        )
    assert http_calls == []


def test_text_probe_requires_pong_and_counts_before_http(ready_config):
    seen: list[int] = []

    def wrong_body(url, *, headers, json, timeout):
        assert seen == [1]
        assert json["messages"] == TEXT_PROBE_MESSAGES
        assert json["temperature"] == 0.4
        assert url == f"{SECRET_BASE_URL.rstrip('/')}/chat/completions"
        return {
            "choices": [{"message": {"content": "ping"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    with pytest.raises(PreflightError, match="pong") as failed:
        run_preflight(
            ready_config,
            session=_session(),
            probe_text=True,
            confirm_text_requests=1,
            http_post=wrong_body,
            request_count=seen,
        )
    assert seen == [1]
    assert failed.value.text_requests_counted == 1


def test_text_probe_accepts_stripped_pong_and_records_usage(ready_config):
    def pong(url, *, headers, json, timeout):
        assert json["messages"] == TEXT_PROBE_MESSAGES
        assert json["temperature"] == 0.4
        assert timeout == 8
        assert headers["Authorization"] == f"Bearer {SECRET_API_KEY}"
        return {
            "provider": "test-provider",
            "model": "returned-model",
            "choices": [{"message": {"content": "  pong  "}}],
            "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9},
        }

    result = run_preflight(
        ready_config,
        session=_session(),
        probe_text=True,
        confirm_text_requests=1,
        http_post=pong,
    )
    assert result.text_probe is not None
    assert result.text_probe.provider == "test-provider"
    assert result.text_probe.model == "returned-model"
    assert result.text_probe.usage == {
        "prompt_tokens": 8,
        "completion_tokens": 1,
        "total_tokens": 9,
    }
    assert result.text_probe.requests_counted == 1


def test_text_probe_does_not_log_key_or_headers(ready_config, caplog):
    def explode(url, *, headers, json, timeout):
        raise RuntimeError(f"boom {headers}")

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PreflightError, match="text probe") as failed:
            run_preflight(
                ready_config,
                session=_session(),
                probe_text=True,
                confirm_text_requests=1,
                http_post=explode,
            )
    rendered = str(failed.value) + caplog.text
    assert SECRET_API_KEY not in rendered
    assert "Authorization" not in rendered
    assert SECRET_OBS_PASSWORD not in rendered


def test_successful_preflight_does_not_start_recording_or_submit_fal(
    ready_config,
    monkeypatch,
):
    fal_calls = _fal_spy(monkeypatch)
    client = complete_obs_client()
    result = run_preflight(ready_config, session=ObsSession(client=client))
    assert ("start_record",) not in client.calls
    assert ("stop_record",) not in client.calls
    assert fal_calls == []
    assert result.recording_configured is True
    assert result.streaming is False
    assert result.ffmpeg_path
    assert result.ffprobe_path
    assert "fal_client" not in sys.modules or "runtime_flight.preflight" in sys.modules


def test_check_cli_prints_cap_and_skips_text_http_by_default(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    http_calls: list = []

    def forbidden(*args, **kwargs):
        http_calls.append(1)
        raise AssertionError("default check must not make a text HTTP call")

    code = main(
        ["check", "--config", str(config_path)],
        obs_session=_session(),
        http_post=forbidden,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "12.00" in captured.out
    assert SECRET_API_KEY not in captured.out
    assert SECRET_OBS_PASSWORD not in captured.out
    assert "fal-test-key-not-for-submission" not in captured.out
    assert http_calls == []


def test_check_cli_probe_text_requires_confirm(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    http_calls: list = []

    def forbidden(*args, **kwargs):
        http_calls.append(1)
        raise AssertionError("probe-text alone must not HTTP")

    code = main(
        ["check", "--config", str(config_path), "--probe-text"],
        obs_session=_session(),
        http_post=forbidden,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert http_calls == []
    assert "confirm-text-requests" in captured.err
    assert SECRET_API_KEY not in captured.err


def test_check_cli_probe_text_with_confirm_runs_http(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "check",
            "--config",
            str(config_path),
            "--probe-text",
            "--confirm-text-requests",
            "1",
        ],
        obs_session=_session(),
        http_post=_pong_response,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "test-provider" in captured.out
    assert SECRET_API_KEY not in captured.out
    assert "Authorization" not in captured.out


def test_preflight_modules_do_not_import_root_scaffold() -> None:
    root = Path(__file__).resolve().parents[1] / "runtime_flight"
    for path in (root / "preflight.py", root / "__main__.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert imported.isdisjoint(FORBIDDEN_ROOT_MODULES)
        assert "fal_client" not in imported
        assert "SourcePacket" not in path.read_text(encoding="utf-8")
