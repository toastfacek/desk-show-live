"""Task 15: safe live flight operator commands."""

from __future__ import annotations

import json
import signal
from pathlib import Path

import pytest

from runtime_flight.__main__ import main
from runtime_flight.obs_session import ObsSession
from runtime_flight.operator import OperatorError
from runtime_flight.signals import install_panic_handler
from test_evidence import make_evidence
from runtime_flight.evidence import write_evidence_bundle
from test_preflight import (
    _complete_env,
    _make_flight_setup,
    _write_flight_config,
    _write_source_files,
)
from conftest_obs import complete_obs_client


@pytest.fixture
def flight_setup(tmp_path: Path) -> dict:
    return _make_flight_setup(tmp_path / "pack-root")


def _session(streaming: bool = False) -> ObsSession:
    client = complete_obs_client()
    client.streaming = streaming
    return ObsSession(client=client)


def test_smoke_refuses_without_paid_flag(
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
            "smoke",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--max-fal-submissions",
            "2",
        ],
        obs_session=_session(),
        flight_runner=lambda **kwargs: 0,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "paid flag absent" in captured.err


def test_live_refuses_cap_confirmation_mismatch(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "live",
            "--config",
            str(config_path),
            "--confirm-spend",
            "1.00",
            "--max-text-requests",
            "24",
        ],
        obs_session=_session(),
        flight_runner=lambda **kwargs: 0,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "confirm-spend" in captured.err


def test_smoke_refuses_unreviewed_source(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    inputs = tmp_path / "inputs"
    written = _write_source_files(inputs)
    packet = json.loads(written["packet"].read_text(encoding="utf-8"))
    packet["reviewed"] = False
    written["packet"].write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")
    config_path = _write_flight_config(tmp_path, flight_setup, source_dir=inputs)
    code = main(
        [
            "smoke",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--max-fal-submissions",
            "2",
        ],
        obs_session=_session(),
        flight_runner=lambda **kwargs: 0,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "reviewed" in captured.err.lower()


def test_setup_obs_refuses_streaming_and_never_stops_stream(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    config_path = _write_flight_config(tmp_path, flight_setup)
    session = _session(streaming=True)
    code = main(
        ["setup-obs", "--config", str(config_path)],
        obs_session=session,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "streaming" in captured.err.lower()
    assert not any(call[0] == "stop_stream" for call in session._client.calls)


def test_smoke_text_request_limit(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "smoke",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--max-fal-submissions",
            "2",
            "--max-text-requests",
            "5",
        ],
        obs_session=_session(),
        flight_runner=lambda **kwargs: 0,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "text request limit" in captured.err


def test_smoke_submission_attempt_limit(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    code = main(
        [
            "smoke",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--max-fal-submissions",
            "3",
        ],
        obs_session=_session(),
        flight_runner=lambda **kwargs: 0,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert "max-fal-submissions" in captured.err


def test_panic_handler_runs_cleanup() -> None:
    cleaned: list[int] = []
    handler = install_panic_handler(lambda: cleaned.append(1), signals=())
    with pytest.raises(SystemExit) as raised:
        handler(signal.SIGINT, None)
    assert raised.value.code == 1
    assert cleaned == [1]


def test_smoke_installs_panic_cleanup(
    tmp_path: Path,
    flight_setup: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _complete_env(monkeypatch, flight_setup)
    monkeypatch.setenv("RUNTIME_ALLOW_PAID", "1")
    config_path = _write_flight_config(tmp_path, flight_setup)
    installed: list[object] = []

    def installer(cleanup):
        installed.append(cleanup)
        return cleanup

    calls: list[dict] = []

    def runner(**kwargs):
        calls.append(kwargs)
        return 0

    code = main(
        [
            "smoke",
            "--config",
            str(config_path),
            "--confirm-spend",
            "12.00",
            "--max-fal-submissions",
            "2",
        ],
        obs_session=_session(),
        flight_runner=runner,
        panic_installer=installer,
        cleanup=lambda: None,
    )
    assert code == 0
    assert installed
    assert calls and calls[0]["mode"] == "smoke"


def test_replay_performs_no_network(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence = make_evidence(tmp_path)
    bundle = write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)

    def forbidden(*args, **kwargs):
        raise AssertionError("replay must not make a network call")

    code = main(
        ["replay", "--dir", str(bundle)],
        network_call=None,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "replay: true" in captured.out
    with pytest.raises(OperatorError, match="network"):
        from runtime_flight.operator import cmd_replay

        cmd_replay(bundle, network_call=forbidden)


def test_verify_flight_cli_automated(tmp_path: Path) -> None:
    evidence = make_evidence(tmp_path)
    bundle = write_evidence_bundle(tmp_path / "out" / "flights", evidence, sleep=lambda _dt: None)

    class Result:
        exit_code = 0

    code = main(
        ["verify-flight", "--automated", "--dir", str(bundle)],
        verify=lambda _bundle, mode: Result(),
    )
    assert code == 0
