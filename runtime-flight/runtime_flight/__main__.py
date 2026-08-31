from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from runtime_flight.config import (
    ConfigError,
    REDACTED,
    load_config,
    redacted_summary,
    validate_config,
)
from runtime_flight.obs_session import ObsSession
from runtime_flight.preflight import (
    PreflightError,
    open_obs_session,
    preflight_report,
    run_preflight,
)


def main(
    argv: list[str] | None = None,
    *,
    obs_session: ObsSession | None = None,
    http_post=None,
) -> int:
    parser = argparse.ArgumentParser(prog="runtime_flight")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check",
        help="Validate flight configuration and run no-video preflight probes.",
    )
    check_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to the flight YAML configuration file.",
    )
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

    args = parser.parse_args(argv)
    if args.command == "check":
        return _cmd_check(
            args.config,
            probe_text=args.probe_text,
            confirm_text_requests=args.confirm_text_requests,
            obs_session=obs_session,
            http_post=http_post,
        )
    raise AssertionError(f"unhandled command: {args.command}")


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
