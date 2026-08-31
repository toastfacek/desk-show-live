"""OBS box config keeps credentials and output paths local to the checkout."""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_ROOT))

import obs_box_config


def test_ensure_password_persists_environment_selected_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_path = tmp_path / "desk-show" / "obs.env"
    monkeypatch.setattr(obs_box_config, "SECRET_PATH", secret_path)
    monkeypatch.setenv(obs_box_config.ENV_NAME, "password-from-environment")

    password = obs_box_config.ensure_password()

    assert password == "password-from-environment"
    assert secret_path.read_text(encoding="utf-8") == (
        "OBS_WEBSOCKET_PASSWORD=password-from-environment\n"
    )
    assert stat.S_IMODE(secret_path.stat().st_mode) == 0o600


def test_ensure_password_replaces_stale_secret_file_when_environment_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_path = tmp_path / "desk-show" / "obs.env"
    secret_path.parent.mkdir()
    secret_path.write_text("OBS_WEBSOCKET_PASSWORD=stale-password\n", encoding="utf-8")
    monkeypatch.setattr(obs_box_config, "SECRET_PATH", secret_path)
    monkeypatch.setenv(obs_box_config.ENV_NAME, "current-password")

    assert obs_box_config.ensure_password() == "current-password"
    assert "current-password" in secret_path.read_text(encoding="utf-8")
    assert "stale-password" not in secret_path.read_text(encoding="utf-8")


def test_write_obs_files_uses_requested_record_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_dir = tmp_path / "obs-studio"
    record_dir = tmp_path / "recordings"
    monkeypatch.setattr(obs_box_config, "CONFIG_DIR", config_dir)

    obs_box_config.write_obs_files(
        password="test-password",
        port=4555,
        record_dir=record_dir,
    )

    websocket = config_dir / "plugin_config" / "obs-websocket" / "config.json"
    assert '"server_port": 4555' in websocket.read_text(encoding="utf-8")
    basic = config_dir / "basic" / "profiles" / "Untitled" / "basic.ini"
    assert f"FilePath={record_dir.resolve()}" in basic.read_text(encoding="utf-8")
    assert record_dir.is_dir()
