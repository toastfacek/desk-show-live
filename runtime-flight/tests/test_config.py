from __future__ import annotations

import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from runtime_flight.config import (
    ConfigError,
    apply_source_dir,
    load_config,
    redacted_summary,
    validate_config,
    validate_obs_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_FLIGHT_ROOT = Path(__file__).resolve().parents[1]

SECRET_BASE_URL = "https://text.example.invalid/v1"
SECRET_API_KEY = "sk-test-text-api-key-abcdef0123456789"
SECRET_OBS_PASSWORD = "obs-ws-password-secret-value"
SECRET_BASELINE_ID = "baseline-test-uuid-0001"


def _minimal_config(**overrides) -> dict:
    config = {
        "mode": "live",
        "pack_manager_data_dir": "../pack-manager/data",
        "baseline_id_env": "RUNTIME_BASELINE_ID",
        "source_packet": "inputs/source_packet.local.json",
        "source_lock": "inputs/source_packet.lock.json",
        "target_duration_s": 90,
        "text": {
            "base_url_env": "TEXT_BASE_URL",
            "api_key_env": "TEXT_API_KEY",
            "model_env": "TEXT_MODEL",
            "timeout_s": 8,
            "smoke_max_requests": 4,
            "flight_max_requests": 24,
        },
        "video": {
            "endpoint": "minimax/h3-max/image-to-video",
            "duration_s": 5,
            "resolution": "768P",
            "prompt_expansion_mode": "balanced",
            "safety_checker": True,
        },
        "spend": {
            "cap_env": "RUNTIME_SPEND_CAP_USD",
            "rate_768p_usd_per_s": 0.08,
        },
        "obs": {
            "host": "127.0.0.1",
            "port": 4455,
            "password_env": "OBS_WEBSOCKET_PASSWORD",
            "record": True,
        },
        "stream": {
            "enabled": False,
        },
    }
    config.update(overrides)
    return config


def _write_config(tmp_path: Path, payload: dict | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(payload or _minimal_config(), sort_keys=False))
    return config_path


def _set_complete_env(monkeypatch: pytest.MonkeyPatch, *, cap: str = "12.00") -> None:
    monkeypatch.setenv("RUNTIME_BASELINE_ID", SECRET_BASELINE_ID)
    monkeypatch.setenv("TEXT_BASE_URL", SECRET_BASE_URL)
    monkeypatch.setenv("TEXT_API_KEY", SECRET_API_KEY)
    monkeypatch.setenv("TEXT_MODEL", "test-model")
    monkeypatch.setenv("RUNTIME_SPEND_CAP_USD", cap)
    monkeypatch.setenv("OBS_WEBSOCKET_PASSWORD", SECRET_OBS_PASSWORD)


def test_example_config_documents_root_scaffold_is_not_flight_config() -> None:
  example = (RUNTIME_FLIGHT_ROOT / "config.example.yaml").read_text(encoding="utf-8")
  assert "config.yaml" in example
  assert "requirements.txt" in example
  assert "not flight configuration" in example.lower()


def test_load_config_resolves_paths_relative_to_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "flight"
    config_dir.mkdir()
    config_path = _write_config(config_dir)
    _set_complete_env(monkeypatch)

    loaded = load_config(config_path)

    assert loaded.pack_manager_data_dir == (
        config_dir / "../pack-manager/data"
    ).resolve()
    assert loaded.source_packet == (config_dir / "inputs/source_packet.local.json").resolve()
    assert loaded.source_lock == (config_dir / "inputs/source_packet.lock.json").resolve()


def test_apply_source_dir_overrides_packet_and_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "flight"
    config_dir.mkdir()
    config_path = _write_config(config_dir)
    _set_complete_env(monkeypatch)
    staged = tmp_path / "staged" / "123"
    staged.mkdir(parents=True)
    packet = staged / "source_packet.local.json"
    lock = staged / "source_packet.lock.json"
    packet.write_text("{}", encoding="utf-8")
    lock.write_text("{}", encoding="utf-8")
    loaded = apply_source_dir(load_config(config_path), staged)
    assert loaded.source_packet == packet.resolve()
    assert loaded.source_lock == lock.resolve()
    with pytest.raises(ConfigError, match="source-dir"):
        apply_source_dir(load_config(config_path), tmp_path / "missing")


def test_validate_config_rejects_missing_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    _set_complete_env(monkeypatch)
    monkeypatch.delenv("TEXT_API_KEY", raising=False)

    loaded = load_config(config_path)

    with pytest.raises(ConfigError, match="TEXT_API_KEY"):
        validate_config(loaded)

    try:
        validate_config(loaded)
    except ConfigError as error:
        rendered = str(error)
        assert SECRET_API_KEY not in rendered
        assert SECRET_OBS_PASSWORD not in rendered
        assert SECRET_BASE_URL not in rendered
    else:
        raise AssertionError("expected ConfigError")


def test_validate_config_segment_skips_obs_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    _set_complete_env(monkeypatch)
    monkeypatch.delenv("OBS_WEBSOCKET_PASSWORD", raising=False)
    loaded = load_config(config_path)
    validate_config(loaded, require_obs=False)
    with pytest.raises(ConfigError, match="OBS_WEBSOCKET_PASSWORD"):
        validate_config(loaded)


def test_validate_obs_config_does_not_require_flight_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    for name in (
        "RUNTIME_BASELINE_ID",
        "TEXT_BASE_URL",
        "TEXT_API_KEY",
        "TEXT_MODEL",
        "RUNTIME_SPEND_CAP_USD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OBS_WEBSOCKET_PASSWORD", SECRET_OBS_PASSWORD)

    validate_obs_config(load_config(config_path))


@pytest.mark.parametrize(
    ("mode", "cap", "message"),
    [
        ("live", "12.01", "12.00"),
        ("live", "0", "greater than zero"),
        ("live", "-1.00", "greater than zero"),
        ("live", "not-a-number", "decimal"),
        ("smoke", "2.01", "2.00"),
    ],
)
def test_validate_config_rejects_invalid_caps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    cap: str,
    message: str,
) -> None:
    config_path = _write_config(tmp_path, _minimal_config(mode=mode))
    _set_complete_env(monkeypatch, cap=cap)

    loaded = load_config(config_path)

    with pytest.raises(ConfigError, match=message):
        validate_config(loaded)


def test_validate_config_rejects_streaming_enabled(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        _minimal_config(stream={"enabled": True}),
    )

    loaded = load_config(config_path)

    with pytest.raises(ConfigError, match="stream.enabled"):
        validate_config(loaded)


@pytest.mark.parametrize(
    "video_patch,message",
    [
        ({"endpoint": "other/model"}, "endpoint"),
        ({"duration_s": 6}, "duration_s"),
        ({"resolution": "480P"}, "resolution"),
        ({"prompt_expansion_mode": "quality"}, "prompt_expansion_mode"),
        ({"safety_checker": False}, "safety_checker"),
    ],
)
def test_validate_config_enforces_video_restrictions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    video_patch: dict,
    message: str,
) -> None:
    video = _minimal_config()["video"] | video_patch
    config_path = _write_config(tmp_path, _minimal_config(video=video))
    _set_complete_env(monkeypatch)

    loaded = load_config(config_path)

    with pytest.raises(ConfigError, match=message):
        validate_config(loaded)


def test_secret_redaction_in_repr_errors_and_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    _set_complete_env(monkeypatch)
    monkeypatch.delenv("TEXT_MODEL", raising=False)

    loaded = load_config(config_path)
    summary = redacted_summary(loaded)
    rendered = json.dumps(summary)

    for secret in (SECRET_API_KEY, SECRET_OBS_PASSWORD, SECRET_BASE_URL):
        assert secret not in repr(loaded)
        assert secret not in str(loaded)
        assert secret not in rendered

    assert summary["text"]["api_key_env"] == "TEXT_API_KEY"
    assert summary["text"]["api_key"] == "<redacted>"
    assert summary["obs"]["password"] == "<redacted>"

    try:
        validate_config(loaded)
    except ConfigError as error:
        assert SECRET_API_KEY not in str(error)
        assert SECRET_OBS_PASSWORD not in str(error)
    else:
        raise AssertionError("expected ConfigError")


def test_validate_config_accepts_complete_live_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    _set_complete_env(monkeypatch, cap="12.00")

    loaded = load_config(config_path)
    validate_config(loaded)

    assert loaded.baseline_id == SECRET_BASELINE_ID
    assert loaded.spend_cap_usd == Decimal("12.00")
    assert loaded.spend_rate_768p_usd_per_s == Decimal("0.08")


def test_check_cli_prints_redacted_summary_and_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)
    _set_complete_env(monkeypatch, cap="12.00")

    from runtime_flight.__main__ import main
    from runtime_flight.preflight import PreflightResult

    monkeypatch.setattr(
        "runtime_flight.__main__.run_preflight",
        lambda config, **kwargs: PreflightResult(
            ffmpeg_path="/usr/bin/ffmpeg",
            ffprobe_path="/usr/bin/ffprobe",
            streaming=False,
            recording_configured=True,
            fal_key_present=True,
            spend_cap_usd=Decimal("12.00"),
            text_probe=None,
        ),
    )

    code = main(["check", "--config", str(config_path)], obs_session=object())
    captured = capsys.readouterr()

    assert code == 0, captured.err
    assert SECRET_API_KEY not in captured.out
    assert SECRET_OBS_PASSWORD not in captured.out
    assert "mode: live" in captured.out
    assert "12.00" in captured.out


def test_check_cli_exits_nonzero_for_incomplete_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    _set_complete_env(monkeypatch)
    monkeypatch.delenv("RUNTIME_BASELINE_ID", raising=False)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runtime_flight",
            "check",
            "--config",
            str(config_path),
        ],
        cwd=RUNTIME_FLIGHT_ROOT,
        env={**os.environ},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert SECRET_API_KEY not in result.stderr
    assert "RUNTIME_BASELINE_ID" in result.stderr


def _create_clean_venv(venv_dir: Path) -> Path:
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(venv_dir)],
        check=True,
    )
    python = venv_dir / "bin" / "python"
    bootstrap = subprocess.run(
        [
            "curl",
            "-sS",
            "https://bootstrap.pypa.io/get-pip.py",
        ],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        [str(python), "-"],
        input=bootstrap.stdout,
        check=True,
    )
    return python


def test_clean_venv_imports_all_local_distributions(tmp_path: Path) -> None:
    venv_dir = tmp_path / ".venv"
    python = _create_clean_venv(venv_dir)
    pip = venv_dir / "bin" / "pip"

    install = subprocess.run(
        [
            str(pip),
            "install",
            "-e",
            str(REPO_ROOT / "obs-harness"),
            "-e",
            str(REPO_ROOT / "pack-manager"),
            "-e",
            f"{RUNTIME_FLIGHT_ROOT}[dev]",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    probe = subprocess.run(
        [
            str(python),
            "-c",
            "import obs_harness, pack_manager, runtime_flight; "
            "from runtime_flight.config import load_config",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
