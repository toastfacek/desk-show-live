"""Write local OBS 28+ config so the harness can start Studio without a GUI."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

ENV_NAME = "OBS_WEBSOCKET_PASSWORD"
DEFAULT_PORT = 4455
CONFIG_DIR = Path.home() / ".config" / "obs-studio"
SECRET_PATH = Path.home() / ".config" / "desk-show" / "obs.env"


def _read_secret_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{ENV_NAME}="):
            value = line.split("=", 1)[1].strip()
            return value or None
    return None


def ensure_password() -> str:
    existing = os.environ.get(ENV_NAME) or _read_secret_file(SECRET_PATH)
    if existing:
        os.environ[ENV_NAME] = existing
        return existing
    password = secrets.token_urlsafe(24)
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRET_PATH.write_text(f"{ENV_NAME}={password}\n", encoding="utf-8")
    SECRET_PATH.chmod(0o600)
    os.environ[ENV_NAME] = password
    return password


def write_obs_files(*, password: str, port: int = DEFAULT_PORT) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "plugin_config" / "obs-websocket").mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "basic" / "profiles" / "Untitled").mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "basic" / "scenes").mkdir(parents=True, exist_ok=True)

    (CONFIG_DIR / "global.ini").write_text(
        "\n".join(
            [
                "[General]",
                "FirstRun=false",
                "LicenseAccepted=true",
                "EnableAutoUpdates=false",
                "LastRunVersion=32.2.0",
                "",
                "[Basic]",
                "Profile=Untitled",
                "ProfileDir=Untitled",
                "SceneCollection=Untitled",
                "SceneCollectionFile=Untitled",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    websocket = {
        "alerts_enabled": False,
        "auth_required": True,
        "first_load": False,
        "server_enabled": True,
        "server_password": password,
        "server_port": int(port),
    }
    (CONFIG_DIR / "plugin_config" / "obs-websocket" / "config.json").write_text(
        json.dumps(websocket, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(CONFIG_DIR / "plugin_config" / "obs-websocket" / "config.json", 0o600)

    record_dir = Path("/workspace/out/obs-recordings")
    record_dir.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "basic" / "profiles" / "Untitled" / "basic.ini").write_text(
        "\n".join(
            [
                "[General]",
                "Name=Untitled",
                "",
                "[Video]",
                "BaseCX=1920",
                "BaseCY=1080",
                "OutputCX=1920",
                "OutputCY=1080",
                "FPSType=0",
                "FPSCommon=30",
                "ColorFormat=NV12",
                "ColorSpace=709",
                "ColorRange=Partial",
                "ScaleType=bicubic",
                "",
                "[Output]",
                "Mode=Simple",
                "",
                "[SimpleOutput]",
                f"FilePath={record_dir}",
                "RecFormat2=mkv",
                "RecQuality=Small",
                "VBitrate=2500",
                "ABitrate=160",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    password = ensure_password()
    write_obs_files(password=password)
    print(f"{ENV_NAME} ready (length {len(password)})")
    print(f"secret_file={SECRET_PATH}")
    print(f"obs_config={CONFIG_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
