from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import yaml

from runtime_flight.clip import ALLOWED_VIDEO_DURATIONS_S

ALLOWED_VIDEO_ENDPOINTS = frozenset(
    {
        "minimax/h3-max/image-to-video",
        "minimax/h3-max-turbo/image-to-video",
    }
)

LIVE_CAP_MAX_USD = Decimal("12.00")
SMOKE_CAP_MAX_USD = Decimal("2.00")
REDACTED = "<redacted>"


class ConfigError(Exception):
    """Raised when flight configuration is incomplete or invalid."""


@dataclass(frozen=True)
class RuntimeConfig:
    mode: Literal["live", "smoke"]
    pack_manager_data_dir: Path
    baseline_id_env: str
    baseline_id: str | None
    source_packet: Path
    source_lock: Path
    target_duration_s: int
    text_base_url_env: str
    text_api_key_env: str
    text_model_env: str
    text_base_url: str | None
    text_api_key: str | None
    text_model: str | None
    text_timeout_s: int
    text_smoke_max_requests: int
    text_flight_max_requests: int
    video_endpoint: str
    video_duration_s: int
    video_resolution: str
    video_prompt_expansion_mode: str
    video_safety_checker: bool
    spend_cap_env: str
    spend_cap_usd: Decimal | None
    spend_rate_768p_usd_per_s: Decimal
    obs_host: str
    obs_port: int
    obs_password_env: str
    obs_password: str | None
    obs_record: bool
    stream_enabled: bool

    def __repr__(self) -> str:
        return _redact_known_secrets(super().__repr__(), self._secret_values())

    def __str__(self) -> str:
        return _redact_known_secrets(super().__str__(), self._secret_values())

    def _secret_values(self) -> tuple[str, ...]:
        values: list[str] = []
        for value in (
            self.baseline_id,
            self.text_base_url,
            self.text_api_key,
            self.obs_password,
        ):
            if value:
                values.append(value)
        return tuple(values)


def load_config(path: Path) -> RuntimeConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"config file not found: {path}") from error
    if not isinstance(raw, dict):
        raise ConfigError("config must be a YAML object")

    base_dir = path.parent.resolve()
    mode = _require_str(raw, "mode")
    if mode not in {"live", "smoke"}:
        raise ConfigError("mode must be 'live' or 'smoke'")

    text = _require_mapping(raw, "text")
    video = _require_mapping(raw, "video")
    spend = _require_mapping(raw, "spend")
    obs = _require_mapping(raw, "obs")
    stream = _require_mapping(raw, "stream")

    baseline_id_env = _require_str(raw, "baseline_id_env")
    text_base_url_env = _require_str(text, "base_url_env")
    text_api_key_env = _require_str(text, "api_key_env")
    text_model_env = _require_str(text, "model_env")
    spend_cap_env = _require_str(spend, "cap_env")
    obs_password_env = _require_str(obs, "password_env")

    return RuntimeConfig(
        mode=mode,
        pack_manager_data_dir=_resolve_path(base_dir, _require_str(raw, "pack_manager_data_dir")),
        baseline_id_env=baseline_id_env,
        baseline_id=_read_env(baseline_id_env),
        source_packet=_resolve_path(base_dir, _require_str(raw, "source_packet")),
        source_lock=_resolve_path(base_dir, _require_str(raw, "source_lock")),
        target_duration_s=_require_int(raw, "target_duration_s"),
        text_base_url_env=text_base_url_env,
        text_api_key_env=text_api_key_env,
        text_model_env=text_model_env,
        text_base_url=_read_env(text_base_url_env),
        text_api_key=_read_env(text_api_key_env),
        text_model=_resolve_text_model(text, text_model_env),
        text_timeout_s=_require_int(text, "timeout_s"),
        text_smoke_max_requests=_require_int(text, "smoke_max_requests"),
        text_flight_max_requests=_require_int(text, "flight_max_requests"),
        video_endpoint=_require_str(video, "endpoint"),
        video_duration_s=_require_int(video, "duration_s"),
        video_resolution=_require_str(video, "resolution"),
        video_prompt_expansion_mode=_require_str(video, "prompt_expansion_mode"),
        video_safety_checker=_require_bool(video, "safety_checker"),
        spend_cap_env=spend_cap_env,
        spend_cap_usd=_read_decimal_env(spend_cap_env),
        spend_rate_768p_usd_per_s=_require_decimal(spend, "rate_768p_usd_per_s"),
        obs_host=_require_str(obs, "host"),
        obs_port=_require_int(obs, "port"),
        obs_password_env=obs_password_env,
        obs_password=_read_env(obs_password_env),
        obs_record=_require_bool(obs, "record"),
        stream_enabled=_require_bool(stream, "enabled"),
    )


def apply_source_dir(config: RuntimeConfig, source_dir: Path) -> RuntimeConfig:
    root = Path(source_dir).resolve()
    packet = root / "source_packet.local.json"
    lock = root / "source_packet.lock.json"
    if not packet.is_file() or not lock.is_file():
        raise ConfigError(
            "source-dir must contain source_packet.local.json and source_packet.lock.json"
        )
    return replace(config, source_packet=packet, source_lock=lock)


def validate_obs_config(config: RuntimeConfig) -> None:
    """Validate only the settings needed to connect to and prepare OBS."""
    errors: list[str] = []

    if not config.obs_password:
        errors.append(f"missing required environment variable: {config.obs_password_env}")
    if not 1 <= config.obs_port <= 65_535:
        errors.append("obs.port must be between 1 and 65535")
    if config.stream_enabled:
        errors.append("stream.enabled must be false")
    if not config.obs_record:
        errors.append("obs.record must be true")

    if errors:
        raise ConfigError(_redact_known_secrets("; ".join(errors), config._secret_values()))


def validate_config(config: RuntimeConfig, *, require_obs: bool = True) -> None:
    errors: list[str] = []

    required_env = [
        (config.baseline_id_env, config.baseline_id),
        (config.text_base_url_env, config.text_base_url),
        (config.text_api_key_env, config.text_api_key),
    ]
    if require_obs:
        required_env.append((config.obs_password_env, config.obs_password))
    for env_name, value in required_env:
        if not value:
            errors.append(f"missing required environment variable: {env_name}")
    if not config.text_model:
        errors.append("text.model missing (set text.model in yaml or TEXT_MODEL)")

    if config.spend_cap_usd is None:
        if os.environ.get(config.spend_cap_env, "") != "":
            errors.append(f"{config.spend_cap_env} must be a decimal number")
        else:
            errors.append(f"missing required environment variable: {config.spend_cap_env}")
    elif config.spend_cap_usd <= 0:
        errors.append("spend cap must be greater than zero")
    else:
        cap_max = LIVE_CAP_MAX_USD if config.mode == "live" else SMOKE_CAP_MAX_USD
        if config.spend_cap_usd > cap_max:
            errors.append(
                f"spend cap must be at most {cap_max} USD for mode {config.mode!r}"
            )

    if config.stream_enabled:
        errors.append("stream.enabled must be false")

    if not config.obs_record:
        errors.append("obs.record must be true")

    if config.target_duration_s < 90:
        errors.append("target_duration_s must be at least 90")

    if config.video_endpoint not in ALLOWED_VIDEO_ENDPOINTS:
        errors.append(
            "video.endpoint must be minimax/h3-max/image-to-video "
            "or minimax/h3-max-turbo/image-to-video"
        )
    if config.video_duration_s not in ALLOWED_VIDEO_DURATIONS_S:
        errors.append("video.duration_s must be 5, 10, or 15")
    if config.video_resolution != "768P":
        errors.append("video.resolution must be 768P")
    if config.video_prompt_expansion_mode != "balanced":
        errors.append("video.prompt_expansion_mode must be balanced")
    if not config.video_safety_checker:
        errors.append("video.safety_checker must be true")

    if errors:
        raise ConfigError(_redact_known_secrets("; ".join(errors), config._secret_values()))


def redacted_summary(config: RuntimeConfig) -> dict[str, Any]:
    return {
        "mode": config.mode,
        "pack_manager_data_dir": str(config.pack_manager_data_dir),
        "baseline_id_env": config.baseline_id_env,
        "baseline_id": REDACTED if config.baseline_id else None,
        "source_packet": str(config.source_packet),
        "source_lock": str(config.source_lock),
        "target_duration_s": config.target_duration_s,
        "text": {
            "base_url_env": config.text_base_url_env,
            "api_key_env": config.text_api_key_env,
            "model_env": config.text_model_env,
            "base_url": REDACTED if config.text_base_url else None,
            "api_key": REDACTED if config.text_api_key else None,
            "model": config.text_model,
            "timeout_s": config.text_timeout_s,
            "smoke_max_requests": config.text_smoke_max_requests,
            "flight_max_requests": config.text_flight_max_requests,
        },
        "video": {
            "endpoint": config.video_endpoint,
            "duration_s": config.video_duration_s,
            "resolution": config.video_resolution,
            "prompt_expansion_mode": config.video_prompt_expansion_mode,
            "safety_checker": config.video_safety_checker,
        },
        "spend": {
            "cap_env": config.spend_cap_env,
            "cap_usd": str(config.spend_cap_usd) if config.spend_cap_usd is not None else None,
            "rate_768p_usd_per_s": str(config.spend_rate_768p_usd_per_s),
        },
        "obs": {
            "host": config.obs_host,
            "port": config.obs_port,
            "password_env": config.obs_password_env,
            "password": REDACTED if config.obs_password else None,
            "record": config.obs_record,
        },
        "stream": {
            "enabled": config.stream_enabled,
        },
    }


def _resolve_text_model(text: dict[str, Any], model_env: str) -> str | None:
    """YAML `text.model` is the visible slug. Env is fallback only."""
    raw = text.get("model")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return _read_env(model_env)


def _read_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    return value


def _read_decimal_env(name: str) -> Decimal | None:
    value = _read_env(name)
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()


def _require_mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a mapping")
    return value


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or value == "":
        raise ConfigError(f"{key} must be a non-empty string")
    return value


def _require_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def _require_bool(raw: dict[str, Any], key: str) -> bool:
    value = raw.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be a boolean")
    return value


def _require_decimal(raw: dict[str, Any], key: str) -> Decimal:
    value = raw.get(key)
    if isinstance(value, bool):
        raise ConfigError(f"{key} must be a decimal number")
    try:
        return Decimal(str(value))
    except InvalidOperation as error:
        raise ConfigError(f"{key} must be a decimal number") from error


def _redact_known_secrets(text: str, secrets: tuple[str, ...]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    return redacted
