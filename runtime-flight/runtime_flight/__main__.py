from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from runtime_flight.config import ConfigError, load_config, redacted_summary, validate_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runtime_flight")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser(
        "check",
        help="Load and validate flight configuration without external probes.",
    )
    check_parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to the flight YAML configuration file.",
    )

    args = parser.parse_args(argv)
    if args.command == "check":
        return _cmd_check(args.config)
    raise AssertionError(f"unhandled command: {args.command}")


def _cmd_check(config_path: Path) -> int:
    try:
        config = load_config(config_path)
        validate_config(config)
    except ConfigError as error:
        print(str(error), file=sys.stderr)
        return 1

    summary = redacted_summary(config)
    print(yaml.safe_dump(summary, sort_keys=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
