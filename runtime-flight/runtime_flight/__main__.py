from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from runtime_flight.discuss import DiscussError, run_discuss
from runtime_flight.config import (
    ConfigError,
    REDACTED,
    load_config,
    redacted_summary,
    validate_config,
    validate_obs_config,
)
from runtime_flight.flight import run_paid_flight, run_rehearsal
from runtime_flight.obs_session import ObsSession
from runtime_flight.obs_setup import DEFAULT_WATCHDOG_URL
from runtime_flight.operator import (
    OperatorError,
    cmd_discuss,
    cmd_paid_flight,
    cmd_replay,
    cmd_segment,
    cmd_setup_obs,
    cmd_verify_flight,
    latest_bundle,
    load_validated_config,
)
from runtime_flight.segment import run_segment
from runtime_flight.preflight import (
    PreflightError,
    open_obs_session,
    preflight_report,
    run_preflight,
)
from runtime_flight.signals import install_panic_handler
from runtime_flight.producer import DEFAULT_PORT, run_board_cli
from runtime_flight.verify import verify_bundle


def main(
    argv: list[str] | None = None,
    *,
    obs_session: ObsSession | None = None,
    http_post=None,
    flight_runner=None,
    rehearsal_runner=None,
    verify=None,
    panic_installer=None,
    cleanup=None,
    network_call=None,
    segment_runner=None,
    discuss_runner=None,
) -> int:
    parser = argparse.ArgumentParser(prog="runtime_flight")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check",
        help="Validate flight configuration and run no-video preflight probes.",
    )
    _add_config_arg(check_parser)
    check_parser.add_argument(
        "--probe-text",
        action="store_true",
        help="Send the explicit one-request text probe. Requires --confirm-text-requests 1.",
    )
    check_parser.add_argument(
        "--confirm-text-requests",
        type=int,
        default=0,
        help="Operator confirmation of text requests to consume. Must be 1 with --probe-text.",
    )

    setup_parser = subparsers.add_parser("setup-obs", help="Create the OBS scene contract.")
    _add_config_arg(setup_parser)
    setup_parser.add_argument(
        "--watchdog-url",
        default=DEFAULT_WATCHDOG_URL,
        help="Loopback URL for the WATCHDOG browser source.",
    )

    rehearse_parser = subparsers.add_parser("rehearse", help="Run a zero-cost rehearsal.")
    _add_config_arg(rehearse_parser)
    rehearse_parser.add_argument(
        "--rundown",
        type=Path,
        default=Path("rundowns/one_tweet_90s.yaml"),
    )

    smoke_parser = subparsers.add_parser("smoke", help="Paid two-submission smoke. Human-gated.")
    _add_paid_args(smoke_parser)
    smoke_parser.add_argument("--max-fal-submissions", type=int, required=True)
    smoke_parser.add_argument("--max-text-requests", type=int, default=6)

    segment_parser = subparsers.add_parser(
        "segment",
        help=(
            "Paid no-OBS segment: talk until the topic is exhausted, "
            "hard-capped at 90s (18 takes). Human-gated."
        ),
    )
    _add_paid_args(segment_parser)
    segment_parser.add_argument("--max-fal-submissions", type=int, default=2)
    segment_parser.add_argument("--max-text-requests", type=int, default=6)

    discuss_parser = subparsers.add_parser(
        "discuss",
        help="Text-only host bounce inspect. No fal. Human-gated text budget.",
    )
    _add_config_arg(discuss_parser)
    discuss_parser.add_argument("--confirm-text-requests", type=int, required=True)
    discuss_parser.add_argument("--max-turns", type=int, default=12)
    discuss_parser.add_argument(
        "--package",
        type=Path,
        help="Reuse a planned segment package and skip the planner call.",
    )

    live_parser = subparsers.add_parser("live", help="Paid 90-second live flight. Human-gated.")
    _add_paid_args(live_parser)
    live_parser.add_argument("--max-text-requests", type=int, default=24)

    replay_parser = subparsers.add_parser("replay", help="Read a finished evidence bundle. No network.")
    _add_bundle_args(replay_parser)

    board_parser = subparsers.add_parser(
        "board",
        help="Open the visual producer harness (demo clock, loopback only).",
    )
    board_parser.add_argument("--host", default="127.0.0.1")
    board_parser.add_argument("--port", type=int, default=DEFAULT_PORT)

    verify_parser = subparsers.add_parser("verify-flight", help="Verify a finished evidence bundle.")
    _add_bundle_args(verify_parser)
    mode = verify_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--automated", action="store_true")
    mode.add_argument("--final", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return _cmd_check(
                args.config,
                probe_text=args.probe_text,
                confirm_text_requests=args.confirm_text_requests,
                obs_session=obs_session,
                http_post=http_post,
            )
        if args.command == "setup-obs":
            config = load_config(args.config)
            validate_obs_config(config)
            session = _session(config, obs_session)
            created = cmd_setup_obs(config, session, watchdog_url=args.watchdog_url)
            print(yaml.safe_dump(created, sort_keys=False), end="")
            return 0
        if args.command == "rehearse":
            if rehearsal_runner is not None:
                return rehearsal_runner(args.rundown)
            config = load_validated_config(args.config)
            return run_rehearsal(config=config, rundown=args.rundown)
        if args.command == "segment":
            config = load_validated_config(args.config, require_obs=False)
            return cmd_segment(
                config,
                confirm_spend=args.confirm_spend,
                max_text_requests=args.max_text_requests,
                max_fal_submissions=args.max_fal_submissions,
                run_segment=segment_runner or run_segment,
            )
        if args.command == "discuss":
            config = load_validated_config(args.config, require_obs=False)
            payload = cmd_discuss(
                config,
                confirm_text_requests=args.confirm_text_requests,
                max_turns=args.max_turns,
                package_path=args.package,
                run_discuss=discuss_runner or run_discuss,
            )
            work_dir = Path(payload["work_dir"])
            print((work_dir / "transcript.txt").read_text(encoding="utf-8"), end="")
            return 0
        if args.command in {"smoke", "live"}:
            config = load_validated_config(args.config)
            session = _session(config, obs_session)

            def _cleanup() -> None:
                try:
                    session.stop_recording()
                except Exception:
                    pass

            return cmd_paid_flight(
                config,
                mode="smoke" if args.command == "smoke" else "live",
                confirm_spend=args.confirm_spend,
                max_text_requests=args.max_text_requests,
                max_fal_submissions=getattr(args, "max_fal_submissions", None),
                session=session,
                run_flight=flight_runner or run_paid_flight,
                cleanup=cleanup or _cleanup,
                panic_installer=panic_installer or install_panic_handler,
            )
        if args.command == "board":
            if args.host not in {"127.0.0.1", "localhost", "::1"}:
                raise OperatorError("producer board must bind loopback only")
            return run_board_cli(host="127.0.0.1" if args.host == "localhost" else args.host, port=args.port)
        if args.command == "replay":
            bundle = _resolve_bundle(args)
            payload = cmd_replay(bundle, network_call=network_call)
            print(yaml.safe_dump({"flight_id": payload.get("flight_id"), "replay": True}, sort_keys=False), end="")
            return 0
        if args.command == "verify-flight":
            bundle = _resolve_bundle(args)
            return cmd_verify_flight(
                bundle,
                mode="final" if args.final else "automated",
                verify=verify or verify_bundle,
            )
        raise AssertionError(f"unhandled command: {args.command}")
    except (ConfigError, PreflightError, OperatorError, DiscussError) as error:
        config = None
        try:
            if hasattr(args, "config"):
                config = load_config(args.config)
        except Exception:
            config = None
        print(_safe_error_text(error, config), file=sys.stderr)
        return 1


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to the flight YAML configuration file.",
    )


def _add_paid_args(parser: argparse.ArgumentParser) -> None:
    _add_config_arg(parser)
    parser.add_argument("--confirm-spend", required=True)


def _add_bundle_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dir", type=Path, dest="bundle_dir")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("out/flights"))


def _resolve_bundle(args) -> Path:
    if args.bundle_dir is not None:
        return args.bundle_dir
    if args.latest:
        return latest_bundle(args.out)
    raise OperatorError("pass --dir or --latest")


def _session(config, obs_session: ObsSession | None) -> ObsSession:
    if obs_session is not None:
        return obs_session
    return open_obs_session(config)


def _cmd_check(
    config_path: Path,
    *,
    probe_text: bool,
    confirm_text_requests: int,
    obs_session: ObsSession | None,
    http_post,
) -> int:
    config = None
    try:
        config = load_config(config_path)
        validate_config(config)
        summary = redacted_summary(config)
        print(yaml.safe_dump(summary, sort_keys=False), end="")

        result = run_preflight(
            config,
            session=obs_session,
            session_factory=(
                None if obs_session is not None else lambda: open_obs_session(config)
            ),
            probe_text=probe_text,
            confirm_text_requests=confirm_text_requests,
            http_post=http_post,
        )
        print(yaml.safe_dump(preflight_report(result), sort_keys=False), end="")
        return 0
    except (ConfigError, PreflightError) as error:
        print(_safe_error_text(error, config), file=sys.stderr)
        return 1


def _safe_error_text(error: Exception, config) -> str:
    text = str(error)
    secrets: list[str] = []
    if config is not None:
        secrets.extend(config._secret_values())
    fal_key = os.environ.get("FAL_KEY")
    if fal_key:
        secrets.append(fal_key)
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text


if __name__ == "__main__":
    raise SystemExit(main())
