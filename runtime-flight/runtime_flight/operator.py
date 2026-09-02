"""Operator command wiring. Gates live here; the harness owns the show clock."""

from __future__ import annotations

import os
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from runtime_flight.config import (
    LIVE_CAP_MAX_USD,
    SMOKE_CAP_MAX_USD,
    RuntimeConfig,
    load_config,
    validate_config,
)
from runtime_flight.fal_gateway import H3_MAX_TURBO_ENDPOINT
from runtime_flight.obs_session import ObsSession
from runtime_flight.obs_setup import setup_obs
from runtime_flight.source import SourceError, load_source_packet
from runtime_flight.stage import StageError, expected_text_requests, run_stage
from runtime_flight.signals import install_panic_handler

PAID_FLAG_ENV = "RUNTIME_ALLOW_PAID"
SMOKE_MAX_TEXT = 6
LIVE_MAX_TEXT = 24
SMOKE_FAL_ATTEMPTS = frozenset({1, 2})
LIVE_SEGMENT_MAX_FAL = 18
DISCUSS_MAX_TURNS = 12


class OperatorError(Exception):
    """Raised when an operator command is refused before work starts."""


FlightRunner = Callable[..., int]


def require_paid_flag() -> None:
    if os.environ.get(PAID_FLAG_ENV) != "1":
        raise OperatorError("paid flag absent")


def require_confirm_spend(config: RuntimeConfig, confirm: str | None) -> Decimal:
    if confirm is None or str(confirm).strip() == "":
        raise OperatorError("confirm-spend does not match spend cap")
    try:
        value = Decimal(str(confirm))
    except InvalidOperation as error:
        raise OperatorError("confirm-spend does not match spend cap") from error
    if config.spend_cap_usd is None or value != config.spend_cap_usd:
        raise OperatorError("confirm-spend does not match spend cap")
    return value


def require_text_request_limit(mode: Literal["smoke", "live"], count: int) -> None:
    limit = SMOKE_MAX_TEXT if mode == "smoke" else LIVE_MAX_TEXT
    if count > limit:
        raise OperatorError(
            f"text request limit exceeded: {count} > {limit} for mode {mode}"
        )


def require_smoke_fal_limit(max_fal_submissions: int) -> None:
    if max_fal_submissions not in SMOKE_FAL_ATTEMPTS:
        raise OperatorError("smoke --max-fal-submissions must be 1 or 2")


def require_segment_fal_limit(
    mode: Literal["smoke", "live"], max_fal_submissions: int
) -> None:
    if mode == "smoke":
        require_smoke_fal_limit(max_fal_submissions)
        return
    if max_fal_submissions < 1 or max_fal_submissions > LIVE_SEGMENT_MAX_FAL:
        raise OperatorError(
            "live segment --max-fal-submissions must be 1 to 18 (90s hard cap)"
        )


def load_reviewed_source(config: RuntimeConfig) -> Any:
    try:
        return load_source_packet(config.source_packet, config.source_lock)
    except SourceError as error:
        raise OperatorError(str(error)) from error


def refuse_active_stream(session: ObsSession) -> None:
    try:
        session.refuse_streaming()
    except RuntimeError as error:
        raise OperatorError(str(error)) from error


def cmd_setup_obs(
    config: RuntimeConfig,
    session: ObsSession,
    *,
    watchdog_url: str,
) -> dict[str, list[str]]:
    refuse_active_stream(session)
    return setup_obs(session._client, watchdog_url=watchdog_url)


def cmd_rehearse(run_rehearsal: Callable[[], int]) -> int:
    return run_rehearsal()


def cmd_paid_flight(
    config: RuntimeConfig,
    *,
    mode: Literal["smoke", "live"],
    confirm_spend: str | None,
    max_text_requests: int,
    max_fal_submissions: int | None,
    session: ObsSession,
    run_flight: FlightRunner,
    cleanup: Callable[[], None],
    panic_installer=install_panic_handler,
) -> int:
    require_paid_flag()
    require_confirm_spend(config, confirm_spend)
    require_text_request_limit(mode, max_text_requests)
    if mode == "smoke":
        if max_fal_submissions is None:
            raise OperatorError("smoke --max-fal-submissions must be 1 or 2")
        require_smoke_fal_limit(max_fal_submissions)
    load_reviewed_source(config)
    refuse_active_stream(session)
    panic_installer(cleanup)
    return run_flight(
        config=config,
        mode=mode,
        max_text_requests=max_text_requests,
        max_fal_submissions=max_fal_submissions,
        session=session,
    )


def cmd_segment(
    config: RuntimeConfig,
    *,
    confirm_spend: str | None,
    max_text_requests: int,
    max_fal_submissions: int,
    run_segment: FlightRunner,
) -> int:
    require_paid_flag()
    require_confirm_spend(config, confirm_spend)
    require_text_request_limit(config.mode, max_text_requests)
    require_segment_fal_limit(config.mode, max_fal_submissions)
    cap_max = SMOKE_CAP_MAX_USD if config.mode == "smoke" else LIVE_CAP_MAX_USD
    if config.spend_cap_usd is None or config.spend_cap_usd > cap_max:
        raise OperatorError(f"segment spend cap must be at most {cap_max}")
    load_reviewed_source(config)
    return run_segment(
        config=config,
        max_text_requests=max_text_requests,
        max_fal_submissions=max_fal_submissions,
    )


def cmd_discuss(
    config: RuntimeConfig,
    *,
    confirm_text_requests: int,
    max_turns: int,
    package_path: Path | None,
    run_discuss,
    load_package=None,
) -> dict[str, Any]:
    if package_path is None:
        if confirm_text_requests != max_turns + 1:
            raise OperatorError(
                "discuss --confirm-text-requests must be --max-turns plus one planner call"
            )
    elif confirm_text_requests != max_turns:
        raise OperatorError(
            "discuss --confirm-text-requests must match --max-turns when a package is supplied"
        )
    if max_turns < 1 or max_turns > DISCUSS_MAX_TURNS:
        raise OperatorError("discuss --max-turns must be 1 to 12")
    require_text_request_limit(config.mode, confirm_text_requests)
    load_reviewed_source(config)
    package = None
    if package_path is not None:
        loader = load_package
        if loader is None:
            from runtime_flight.discuss import load_package as loader
        package = loader(package_path)
    return run_discuss(
        config=config,
        max_text_requests=confirm_text_requests,
        max_turns=max_turns,
        package=package,
    )


def cmd_stage(
    config: RuntimeConfig,
    *,
    tweet_url: str,
    out_dir: Path,
    confirm_text_requests: int,
    plan: bool,
    write: bool,
    keep_overlay: bool,
    overlay_port: int,
    fixture_path: Path | None,
    run_stage_fn=run_stage,
    http_get=None,
    http_post=None,
    overlay=None,
) -> dict[str, Any]:
    if write:
        plan = True
    needed = expected_text_requests(plan=plan, write=write)
    if needed:
        if confirm_text_requests != needed:
            raise OperatorError(
                f"stage --confirm-text-requests must be {needed} for this mode"
            )
        require_text_request_limit(config.mode, confirm_text_requests)
    elif confirm_text_requests not in {0, needed}:
        raise OperatorError("stage ingest-only does not consume text requests")
    fixture = None
    if fixture_path is not None:
        import json

        try:
            raw = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise OperatorError("tweet fixture is not valid JSON") from error
        if not isinstance(raw, dict):
            raise OperatorError("tweet fixture must be a JSON object")
        fixture = raw
    try:
        return run_stage_fn(
            tweet_url=tweet_url,
            config=config,
            out_dir=out_dir,
            confirm_text_requests=confirm_text_requests,
            plan=plan,
            write=write,
            overlay_port=overlay_port,
            keep_overlay=keep_overlay,
            fixture=fixture,
            http_get=http_get,
            http_post=http_post,
            overlay=overlay,
        )
    except StageError as error:
        raise OperatorError(str(error)) from error


def cmd_time_fal(
    config: RuntimeConfig,
    *,
    confirm_spend: str | None,
    takes: int,
    duration_s: int,
    run_time_fal,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    require_paid_flag()
    require_confirm_spend(config, confirm_spend)
    if takes < 1 or takes > 3:
        raise OperatorError("time-fal --takes must be 1 to 3")
    if duration_s != 5:
        raise OperatorError("time-fal --duration must be 5")
    return run_time_fal(
        config=config,
        takes=takes,
        duration_s=duration_s,
        out_dir=out_dir,
    )


def cmd_prepare_pass(
    config: RuntimeConfig,
    *,
    confirm_spend: str | None,
    endpoint: str,
    duration_s: int,
    rate: str,
    run_prepare_pass,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    from runtime_flight.prepare_pass import apply_prepare_overrides, parse_prepare_rate

    require_paid_flag()
    require_confirm_spend(config, confirm_spend)
    if duration_s != 5:
        raise OperatorError("prepare-pass --duration must be 5")
    updated = apply_prepare_overrides(
        config,
        endpoint=endpoint or H3_MAX_TURBO_ENDPOINT,
        duration_s=duration_s,
        rate_768p_usd_per_s=parse_prepare_rate(rate),
    )
    validate_config(updated, require_obs=False)
    return run_prepare_pass(config=updated, out_dir=out_dir)


def cmd_replay(bundle: Path, *, network_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    if network_call is not None:
        raise OperatorError("replay performs no network calls")
    flight_path = Path(bundle) / "flight.json"
    if not flight_path.is_file():
        raise OperatorError("replay evidence bundle is missing flight.json")
    import json

    return json.loads(flight_path.read_text(encoding="utf-8"))


def cmd_verify_flight(
    bundle: Path,
    *,
    mode: Literal["automated", "final"],
    verify,
) -> int:
    result = verify(Path(bundle), mode=mode)
    return int(result.exit_code)


def latest_bundle(out_dir: Path) -> Path:
    root = Path(out_dir)
    if not root.is_dir():
        raise OperatorError(f"no flights directory: {root}")
    children = [path for path in root.iterdir() if path.is_dir()]
    if not children:
        raise OperatorError("no flight evidence bundles")
    return max(children, key=lambda path: path.stat().st_mtime)


def load_validated_config(path: Path, *, require_obs: bool = True) -> RuntimeConfig:
    config = load_config(path)
    validate_config(config, require_obs=require_obs)
    return config
