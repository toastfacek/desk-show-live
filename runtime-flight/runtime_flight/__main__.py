from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import yaml

from runtime_flight.discuss import DiscussError, run_discuss
from runtime_flight.stage import StageError
from runtime_flight.runway import UntilError
from runtime_flight.tweet_list import TweetListError
from runtime_flight.config import (
    ConfigError,
    REDACTED,
    apply_source_dir,
    load_config,
    redacted_summary,
    validate_config,
    validate_obs_config,
)
from runtime_flight.flight import run_paid_flight, run_rehearsal
from runtime_flight.stage import run_stage
from runtime_flight.obs_session import ObsSession
from runtime_flight.obs_setup import DEFAULT_WATCHDOG_URL
from runtime_flight.fal_gateway import H3_MAX_TURBO_ENDPOINT
from runtime_flight.operator import (
    OperatorError,
    cmd_cook_queue,
    cmd_discuss,
    cmd_enqueue,
    cmd_load_list,
    cmd_paid_flight,
    cmd_prepare_pass,
    cmd_replay,
    cmd_run_list,
    cmd_segment,
    cmd_setup_obs,
    cmd_stage,
    cmd_time_fal,
    cmd_verify_flight,
    latest_bundle,
    load_validated_config,
)
from runtime_flight.prepare_pass import PREPARE_PASS_RATE_USD_PER_S, run_prepare_pass
from runtime_flight.time_fal import run_time_fal
from runtime_flight.timeline import write_timeline
from runtime_flight.segment import run_segment
from runtime_flight.preflight import (
    PreflightError,
    open_obs_session,
    preflight_report,
    run_preflight,
)
from runtime_flight.signals import install_panic_handler
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
    stage_runner=None,
    time_fal_runner=None,
    prepare_pass_runner=None,
    prepare_queue_runner=None,
    cook_queue_runner=None,
    run_list_runner=None,
    http_get=None,
) -> int:
    parser = argparse.ArgumentParser(prog="runtime_flight")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check",
        help="Validate flight configuration and run no-video preflight probes.",
    )
    _add_config_arg(check_parser)
    _add_source_dir_arg(check_parser)
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
    _add_source_dir_arg(rehearse_parser)
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
    _add_source_dir_arg(discuss_parser)
    discuss_parser.add_argument("--confirm-text-requests", type=int, required=True)
    discuss_parser.add_argument("--max-turns", type=int, default=12)
    discuss_parser.add_argument(
        "--package",
        type=Path,
        help="Reuse a planned segment package and skip the planner call.",
    )

    stage_parser = subparsers.add_parser(
        "stage",
        help="Tweet URL → tweet image, producer card, planner, and writer preview.",
    )
    _add_config_arg(stage_parser)
    stage_parser.add_argument("--tweet-url", required=True)
    stage_parser.add_argument(
        "--fixture",
        type=Path,
        help="Offline fetched-tweet JSON. Skips the live tweet HTTP fetch.",
    )
    stage_parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/staged"),
        help="Directory that receives one folder per tweet id.",
    )
    stage_parser.add_argument("--confirm-text-requests", type=int, default=0)
    stage_parser.add_argument(
        "--ingest-only",
        action="store_true",
        help="Write packet, lock, tweet.png, and card. No text model.",
    )
    stage_parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Ingest and planner. Skip the two writer look-ahead lines.",
    )
    stage_parser.add_argument(
        "--keep-overlay",
        action="store_true",
        help="Leave OverlayServer running on --overlay-port after stage.",
    )
    stage_parser.add_argument("--overlay-port", type=int, default=8765)

    live_parser = subparsers.add_parser("live", help="Paid 90-second live flight. Human-gated.")
    _add_paid_args(live_parser)
    live_parser.add_argument("--max-text-requests", type=int, default=24)

    time_fal_parser = subparsers.add_parser(
        "time-fal",
        help="Paid sequential 5s H3 cooks. Logs fal timings.inference. No OBS.",
    )
    _add_paid_args(time_fal_parser)
    time_fal_parser.add_argument("--takes", type=int, default=3)
    time_fal_parser.add_argument("--duration", type=int, default=5)
    time_fal_parser.add_argument(
        "--out",
        type=Path,
        default=Path("out"),
        help="Directory that receives time-fal/<run-id>/.",
    )

    prepare_parser = subparsers.add_parser(
        "prepare-pass",
        help="Cook prepared 5s segments, then concat. No play during cook.",
    )
    _add_paid_args(prepare_parser)
    prepare_parser.add_argument(
        "--endpoint",
        default=H3_MAX_TURBO_ENDPOINT,
        help="H3 image-to-video endpoint. Defaults to H3 Max Turbo.",
    )
    prepare_parser.add_argument("--duration", type=int, default=5)
    prepare_parser.add_argument(
        "--rate",
        default=str(PREPARE_PASS_RATE_USD_PER_S),
        help="768P USD per second. Turbo promo default is 0.01.",
    )
    prepare_parser.add_argument(
        "--out",
        type=Path,
        default=Path("out"),
        help="Directory that receives prepare-pass/<run-id>/.",
    )
    prepare_parser.add_argument(
        "--queue",
        nargs="+",
        type=Path,
        metavar="DIR",
        help="3 to 6 staged tweet directories, in show order. Write each, then cook all takes.",
    )
    prepare_parser.add_argument(
        "--turns",
        type=int,
        default=3,
        help="Spoken takes per tweet. 2 or 3. Only used with --queue.",
    )
    prepare_parser.add_argument(
        "--confirm-text-requests",
        type=int,
        default=0,
        help="Writer budget for --queue. Must be at least the queue length.",
    )

    enqueue_parser = subparsers.add_parser(
        "enqueue",
        help="Drop staged tweet directories into the content inbox. No cook.",
    )
    enqueue_parser.add_argument(
        "--inbox",
        type=Path,
        required=True,
        help="Inbox root with pending/claimed/done/dropped.",
    )
    enqueue_parser.add_argument(
        "source_dirs",
        nargs="+",
        type=Path,
        metavar="DIR",
        help="Staged tweet directories. Producers dissect these; cook-queue dequeues them.",
    )

    cook_parser = subparsers.add_parser(
        "cook-queue",
        help="Dequeue the next dissected tweet and cook until a 45-60s ready buffer. No OBS.",
    )
    _add_paid_args(cook_parser)
    cook_parser.add_argument("--inbox", type=Path, required=True)
    cook_parser.add_argument(
        "--ready-buffer-s",
        type=int,
        default=50,
        help="Stop claiming new tweets once ready plus in-flight tape hits 45-60s.",
    )
    cook_parser.add_argument("--turns", type=int, default=2)
    cook_parser.add_argument("--confirm-text-requests", type=int, required=True)
    cook_parser.add_argument(
        "--endpoint",
        default=H3_MAX_TURBO_ENDPOINT,
        help="H3 image-to-video endpoint. Defaults to H3 Max Turbo.",
    )
    cook_parser.add_argument("--duration", type=int, default=5)
    cook_parser.add_argument(
        "--rate",
        default=str(PREPARE_PASS_RATE_USD_PER_S),
        help="768P USD per second. Turbo promo default is 0.01.",
    )
    cook_parser.add_argument(
        "--out",
        type=Path,
        default=Path("out"),
        help="Directory that receives cook-queue/<run-id>/.",
    )

    load_list_parser = subparsers.add_parser(
        "load-list",
        help="Login-backed Twitter list → inbox pending. Ingest only, no cook.",
    )
    load_list_parser.add_argument("--inbox", type=Path, required=True)
    load_list_parser.add_argument("--list", dest="list_url", help="https://x.com/i/lists/<id>")
    load_list_parser.add_argument(
        "--list-file",
        type=Path,
        help="Offline list snapshot: {list_id, tweets:[{url}, ...]}",
    )

    run_list_parser = subparsers.add_parser(
        "run-list",
        help="Load a Twitter list and comment tweet by tweet until runway runs out. No OBS.",
    )
    _add_paid_args(run_list_parser)
    run_list_parser.add_argument("--inbox", type=Path, required=True)
    run_list_parser.add_argument("--list", dest="list_url", help="https://x.com/i/lists/<id>")
    run_list_parser.add_argument("--list-file", type=Path)
    run_list_parser.add_argument(
        "--until",
        default=None,
        help="Optional ISO-8601 stop. Default: keep going until runway (spend, text, or empty list).",
    )
    run_list_parser.add_argument("--turns", type=int, default=2)
    run_list_parser.add_argument("--confirm-text-requests", type=int, required=True)
    run_list_parser.add_argument(
        "--endpoint",
        default=H3_MAX_TURBO_ENDPOINT,
    )
    run_list_parser.add_argument("--duration", type=int, default=5)
    run_list_parser.add_argument(
        "--rate",
        default=str(PREPARE_PASS_RATE_USD_PER_S),
    )
    run_list_parser.add_argument(
        "--out",
        type=Path,
        default=Path("out"),
    )

    timeline_parser = subparsers.add_parser(
        "timeline",
        help="Render cook waterfall and flame graph HTML from a run directory.",
    )
    timeline_parser.add_argument(
        "--dir",
        type=Path,
        required=True,
        help="time-fal or live work directory (or a fal_cook.jsonl / summary.json).",
    )

    replay_parser = subparsers.add_parser("replay", help="Read a finished evidence bundle. No network.")
    _add_bundle_args(replay_parser)

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
                source_dir=getattr(args, "source_dir", None),
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
            config = _config_with_source(args.config, getattr(args, "source_dir", None))
            return run_rehearsal(config=config, rundown=args.rundown)
        if args.command == "stage":
            plan = not args.ingest_only
            write = plan and not args.plan_only
            config = (
                load_config(args.config)
                if args.ingest_only
                else load_validated_config(args.config, require_obs=False)
            )
            payload = cmd_stage(
                config,
                tweet_url=args.tweet_url,
                out_dir=args.out,
                confirm_text_requests=args.confirm_text_requests,
                plan=plan,
                write=write,
                keep_overlay=args.keep_overlay,
                overlay_port=args.overlay_port,
                fixture_path=args.fixture,
                run_stage_fn=stage_runner or run_stage,
                http_get=http_get,
                http_post=http_post,
            )
            print(yaml.safe_dump(payload, sort_keys=False), end="")
            if args.keep_overlay:
                _hold_overlay()
            return 0
        if args.command == "segment":
            config = _config_with_source(
                args.config, getattr(args, "source_dir", None), require_obs=False
            )
            return cmd_segment(
                config,
                confirm_spend=args.confirm_spend,
                max_text_requests=args.max_text_requests,
                max_fal_submissions=args.max_fal_submissions,
                run_segment=segment_runner or run_segment,
            )
        if args.command == "discuss":
            config = _config_with_source(
                args.config, getattr(args, "source_dir", None), require_obs=False
            )
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
        if args.command == "timeline":
            path = write_timeline(args.dir)
            print(yaml.safe_dump({"timeline_html": str(path)}, sort_keys=False), end="")
            return 0
        if args.command == "time-fal":
            config = load_validated_config(args.config, require_obs=False)
            payload = cmd_time_fal(
                config,
                confirm_spend=args.confirm_spend,
                takes=args.takes,
                duration_s=args.duration,
                run_time_fal=time_fal_runner or run_time_fal,
                out_dir=args.out,
            )
            print(yaml.safe_dump(payload, sort_keys=False), end="")
            return 0
        if args.command == "prepare-pass":
            config = load_validated_config(args.config, require_obs=False)
            payload = cmd_prepare_pass(
                config,
                confirm_spend=args.confirm_spend,
                endpoint=args.endpoint,
                duration_s=args.duration,
                rate=args.rate,
                run_prepare_pass=prepare_pass_runner or run_prepare_pass,
                out_dir=args.out,
                queue=args.queue,
                turns=args.turns,
                confirm_text_requests=args.confirm_text_requests,
                run_prepare_queue=prepare_queue_runner,
                http_post=http_post,
            )
            print(yaml.safe_dump(payload, sort_keys=False), end="")
            return 0
        if args.command == "enqueue":
            payload = cmd_enqueue(inbox=args.inbox, source_dirs=list(args.source_dirs))
            print(yaml.safe_dump(payload, sort_keys=False), end="")
            return 0
        if args.command == "cook-queue":
            config = load_validated_config(args.config, require_obs=False)
            payload = cmd_cook_queue(
                config,
                confirm_spend=args.confirm_spend,
                inbox=args.inbox,
                ready_buffer_s=args.ready_buffer_s,
                turns=args.turns,
                confirm_text_requests=args.confirm_text_requests,
                endpoint=args.endpoint,
                duration_s=args.duration,
                rate=args.rate,
                out_dir=args.out,
                run_cook_queue=cook_queue_runner,
                http_post=http_post,
            )
            print(yaml.safe_dump(payload, sort_keys=False), end="")
            return 0
        if args.command == "load-list":
            payload = cmd_load_list(
                inbox=args.inbox,
                list_url=args.list_url,
                list_file=args.list_file,
                http_get=http_get,
            )
            print(yaml.safe_dump(payload, sort_keys=False), end="")
            return 0
        if args.command == "run-list":
            config = load_validated_config(args.config, require_obs=False)
            payload = cmd_run_list(
                config,
                confirm_spend=args.confirm_spend,
                inbox=args.inbox,
                until=args.until,
                turns=args.turns,
                confirm_text_requests=args.confirm_text_requests,
                endpoint=args.endpoint,
                duration_s=args.duration,
                rate=args.rate,
                list_url=args.list_url,
                list_file=args.list_file,
                out_dir=args.out,
                run_orchestrator=run_list_runner,
                http_get=http_get,
                http_post=http_post,
            )
            print(yaml.safe_dump(payload, sort_keys=False), end="")
            return 0
        if args.command in {"smoke", "live"}:
            config = _config_with_source(args.config, getattr(args, "source_dir", None))
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
    except (
        ConfigError,
        PreflightError,
        OperatorError,
        DiscussError,
        StageError,
        TweetListError,
        UntilError,
    ) as error:
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


def _add_source_dir_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source-dir",
        type=Path,
        help="Staged tweet directory with source_packet.local.json and lock.",
    )


def _config_with_source(
    config_path: Path,
    source_dir: Path | None,
    *,
    require_obs: bool = True,
):
    config = load_validated_config(config_path, require_obs=require_obs)
    if source_dir is None:
        return config
    return apply_source_dir(config, source_dir)


def _add_paid_args(parser: argparse.ArgumentParser) -> None:
    _add_config_arg(parser)
    _add_source_dir_arg(parser)
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


def _hold_overlay() -> None:
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        return


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
    source_dir: Path | None = None,
) -> int:
    config = None
    try:
        config = load_config(config_path)
        if source_dir is not None:
            config = apply_source_dir(config, source_dir)
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
