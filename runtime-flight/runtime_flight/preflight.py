"""No-video live-flight preflight. Verifies files and presence; never submits fal."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from runtime_flight.baseline import BaselineContext
from runtime_flight.config import RuntimeConfig
from runtime_flight.obs_session import ObsSession

MAX_SOURCE_FILE_BYTES = 1024 * 1024
FAL_KEY_ENV = "FAL_KEY"

TEXT_PROBE_MESSAGES = [
    {"role": "system", "content": "Return one lowercase word and nothing else."},
    {"role": "user", "content": "pong"},
]

HttpPost = Callable[..., Any]
SessionFactory = Callable[[], ObsSession]


class PreflightError(Exception):
    """Raised when a preflight probe fails."""

    def __init__(self, message: str, *, text_requests_counted: int = 0) -> None:
        super().__init__(message)
        self.text_requests_counted = text_requests_counted


@dataclass(frozen=True)
class TextProbeResult:
    provider: str | None
    model: str | None
    usage: dict[str, Any]
    requests_counted: int


@dataclass(frozen=True)
class PreflightResult:
    ffmpeg_path: str
    ffprobe_path: str
    streaming: bool
    recording_configured: bool
    fal_key_present: bool
    spend_cap_usd: Decimal
    text_probe: TextProbeResult | None


def submit_fal_job(*_args: Any, **_kwargs: Any) -> None:
    """Reserved helper. Preflight must never submit a fal job."""
    raise RuntimeError("preflight must not submit fal jobs")


def open_obs_session(config: RuntimeConfig) -> ObsSession:
    try:
        from obsws_python import ReqClient
    except ImportError as error:
        raise PreflightError("obsws-python is not installed") from error
    try:
        client = ReqClient(
            host=config.obs_host,
            port=config.obs_port,
            password=config.obs_password or "",
            timeout=3,
        )
    except Exception as error:
        raise PreflightError("OBS connection failed") from error
    return ObsSession(client=client)


def preflight_report(result: PreflightResult) -> dict[str, Any]:
    text_probe: Any
    if result.text_probe is None:
        text_probe = "skipped"
    else:
        text_probe = {
            "provider": result.text_probe.provider,
            "model": result.text_probe.model,
            "usage": result.text_probe.usage,
            "requests_counted": result.text_probe.requests_counted,
        }
    return {
        "confirmed_spend_cap_usd": str(result.spend_cap_usd),
        "preflight": {
            "baseline": "ok",
            "source_packet": "ok",
            "ffmpeg": result.ffmpeg_path,
            "ffprobe": result.ffprobe_path,
            "obs_contract": "ok",
            "streaming": result.streaming,
            "recording_configured": result.recording_configured,
            "text": "present",
            "fal_key": "present" if result.fal_key_present else "missing",
            "text_probe": text_probe,
        },
    }


def run_preflight(
    config: RuntimeConfig,
    *,
    session: ObsSession | None = None,
    session_factory: SessionFactory | None = None,
    probe_text: bool = False,
    confirm_text_requests: int = 0,
    http_post: HttpPost | None = None,
    request_count: list[int] | None = None,
) -> PreflightResult:
    _probe_baseline(config)
    _probe_source_packet(config)
    ffmpeg_path, ffprobe_path = _probe_ffmpeg()
    obs = _resolve_session(session, session_factory)
    _probe_obs_contract(obs)
    _probe_stream_off(obs)
    _probe_recording_configured(config, obs)
    _probe_text_configuration(config)

    text_probe: TextProbeResult | None = None
    if probe_text:
        if confirm_text_requests != 1:
            raise PreflightError("--probe-text requires --confirm-text-requests 1")
        text_probe = _run_text_probe(
            config,
            http_post=http_post,
            request_count=request_count,
        )

    _probe_fal_key_present()
    if config.spend_cap_usd is None:
        raise PreflightError("spend cap is not configured")

    return PreflightResult(
        ffmpeg_path=ffmpeg_path,
        ffprobe_path=ffprobe_path,
        streaming=False,
        recording_configured=True,
        fal_key_present=True,
        spend_cap_usd=config.spend_cap_usd,
        text_probe=text_probe,
    )


def probe_text_completion(
    config: RuntimeConfig,
    *,
    http_post: HttpPost | None = None,
) -> TextProbeResult:
    post = http_post if http_post is not None else _default_http_post
    url = f"{(config.text_base_url or '').rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.text_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.text_model,
        "messages": TEXT_PROBE_MESSAGES,
        "temperature": 0.4,
    }
    try:
        body = post(
            url,
            headers=headers,
            json=payload,
            timeout=float(config.text_timeout_s),
        )
    except PreflightError:
        raise
    except Exception as error:
        raise PreflightError("text probe request failed") from error

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise PreflightError("text probe response missing assistant content") from error
    if not isinstance(content, str) or content.strip() != "pong":
        raise PreflightError("text probe expected body text 'pong'")

    usage = body.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    provider = body.get("provider")
    model = body.get("model")
    return TextProbeResult(
        provider=provider if isinstance(provider, str) else None,
        model=model if isinstance(model, str) else config.text_model,
        usage=usage,
        requests_counted=1,
    )


def _run_text_probe(
    config: RuntimeConfig,
    *,
    http_post: HttpPost | None,
    request_count: list[int] | None,
) -> TextProbeResult:
    budget = (
        config.text_smoke_max_requests
        if config.mode == "smoke"
        else config.text_flight_max_requests
    )
    if 1 > budget:
        raise PreflightError("text probe exceeds request budget")
    if request_count is not None:
        request_count.append(1)
    try:
        return probe_text_completion(config, http_post=http_post)
    except PreflightError as error:
        error.text_requests_counted = 1
        raise


def _default_http_post(
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any],
    timeout: float,
) -> Any:
    import httpx2

    with httpx2.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=json)
        response.raise_for_status()
        return response.json()


def _resolve_session(
    session: ObsSession | None,
    session_factory: SessionFactory | None,
) -> ObsSession:
    if session is not None:
        return session
    if session_factory is None:
        raise PreflightError("OBS session is required")
    return session_factory()


def _probe_baseline(config: RuntimeConfig) -> BaselineContext:
    if not config.baseline_id:
        raise PreflightError("baseline is not configured")
    try:
        return BaselineContext.load(config.pack_manager_data_dir, config.baseline_id)
    except Exception as error:
        raise PreflightError("baseline load failed") from error


def _probe_source_packet(config: RuntimeConfig) -> None:
    packet_root = config.source_packet.parent
    packet_bytes = _read_contained_source_file(
        config.source_packet, packet_root, "source packet"
    )
    lock_bytes = _read_contained_source_file(
        config.source_lock, packet_root, "source lock"
    )
    try:
        packet = json.loads(packet_bytes.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise PreflightError("source packet is not valid JSON") from error
    if not isinstance(packet, dict):
        raise PreflightError("source packet must be a JSON object")
    if packet.get("reviewed") is not True:
        raise PreflightError("source packet is not reviewed")

    tweet = packet.get("tweet")
    if not isinstance(tweet, dict):
        raise PreflightError("source packet tweet text is missing")
    tweet_text = tweet.get("text")
    if not isinstance(tweet_text, str) or tweet_text == "":
        raise PreflightError("source packet tweet text is missing")

    linked = packet.get("linked_source")
    if not isinstance(linked, dict):
        raise PreflightError("source packet excerpt_path is missing")
    excerpt_rel = linked.get("excerpt_path")
    if not isinstance(excerpt_rel, str) or excerpt_rel == "":
        raise PreflightError("source packet excerpt_path is missing")

    excerpt_path = config.source_packet.parent / excerpt_rel
    excerpt_bytes = _read_contained_source_file(excerpt_path, packet_root, "excerpt")

    try:
        lock = json.loads(lock_bytes.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise PreflightError("source lock is not valid JSON") from error
    if not isinstance(lock, dict):
        raise PreflightError("source lock must be a JSON object")
    if not isinstance(lock.get("reviewed_at"), str) or not lock["reviewed_at"]:
        raise PreflightError("source lock missing reviewed_at")

    actual = {
        "source_packet_sha256": hashlib.sha256(
            json.dumps(
                packet,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "tweet_text_sha256": hashlib.sha256(tweet_text.encode("utf-8")).hexdigest(),
        "excerpt_sha256": hashlib.sha256(excerpt_bytes).hexdigest(),
    }
    for key, digest in actual.items():
        if lock.get(key) != digest:
            raise PreflightError(f"{key} mismatch")


def _read_contained_source_file(path: Path, parent: Path, label: str) -> bytes:
    if path.is_symlink():
        raise PreflightError(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError as error:
        raise PreflightError(f"{label} not found") from error
    parent_resolved = parent.resolve()
    if not resolved.is_relative_to(parent_resolved):
        raise PreflightError(f"{label} path escape")
    if resolved.is_symlink() or not resolved.is_file():
        raise PreflightError(f"{label} must be a regular file")
    size = resolved.stat().st_size
    if size == 0:
        raise PreflightError(f"{label} is empty")
    if size > MAX_SOURCE_FILE_BYTES:
        raise PreflightError(f"{label} exceeds 1 MiB")
    data = resolved.read_bytes()
    if not data:
        raise PreflightError(f"{label} is empty")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PreflightError(f"{label} is not valid UTF-8") from error
    return data


def _probe_ffmpeg() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    missing = [
        name
        for name, found in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe))
        if not found
    ]
    if missing:
        raise PreflightError(f"missing on PATH: {', '.join(missing)}")
    return ffmpeg or "", ffprobe or ""


def _probe_obs_contract(session: ObsSession) -> None:
    try:
        session.ensure_contract()
    except Exception as error:
        raise PreflightError(f"OBS contract failed: {error}") from error


def _probe_stream_off(session: ObsSession) -> None:
    try:
        session.refuse_streaming()
    except RuntimeError as error:
        raise PreflightError(str(error)) from error


def _probe_recording_configured(config: RuntimeConfig, session: ObsSession) -> None:
    if not config.obs_record:
        raise PreflightError("recording is not configured")
    try:
        if session._recording_active():
            raise PreflightError("OBS recording is already active")
        session.recording_duration_s()
    except PreflightError:
        raise
    except Exception as error:
        raise PreflightError(f"OBS record status is not readable: {error}") from error


def _probe_text_configuration(config: RuntimeConfig) -> None:
    for env_name, value in (
        (config.text_base_url_env, config.text_base_url),
        (config.text_api_key_env, config.text_api_key),
        (config.text_model_env, config.text_model),
    ):
        if not value:
            raise PreflightError(f"text configuration missing: {env_name}")


def _probe_fal_key_present() -> None:
    value = os.environ.get(FAL_KEY_ENV)
    if not value:
        raise PreflightError(f"missing required environment variable: {FAL_KEY_ENV}")
