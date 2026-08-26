#!/usr/bin/env python3
"""Manual SolMode/GrokMode operator CLI (Task 1R canonical interface).

The ONLY writer of persistent routing mode is an explicit operator command
(``SolMode`` or ``GrokMode``). ``status`` is strictly read-only.

Usage:
    orchestrator_mode.py status [--state-path PATH]
    orchestrator_mode.py SolMode [--state-path PATH]
    orchestrator_mode.py GrokMode [--state-path PATH]

Exit codes:
    0: success
    1: write confirmation mismatch (unexpected)
    2: invalid arguments / unrecognized command
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.runtime_routing_mode import (  # noqa: E402
    GROK_MODE,
    MODE_STATE_PATH_DEFAULT,
    SOL_MODE,
    RoutingMode,
    read_mode,
    write_mode,
)

_SETTERS: dict[str, RoutingMode] = {
    "SolMode": SOL_MODE,
    "GrokMode": GROK_MODE,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrator_mode.py",
        description="View or manually set persistent SolMode/GrokMode state.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=MODE_STATE_PATH_DEFAULT,
        help="authoritative mode.json path (default: %(default)s)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="print current resolved mode (read-only)")
    sub.add_parser(
        "SolMode",
        help="persist SolMode (GPT Plus / Sol / Luna fully eligible)",
    )
    sub.add_parser(
        "GrokMode",
        help="persist GrokMode (entire gpt_plus failure domain excluded)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_path: Path = args.state_path

    if args.command == "status":
        mode = read_mode(state_path)  # strictly read-only by contract
        print(json.dumps({
            "mode": mode.value,
            "state_path": str(state_path),
        }, sort_keys=True))
        return 0

    mode = _SETTERS[args.command]
    write_mode(mode, state_path)
    confirmed = read_mode(state_path)
    print(json.dumps({
        "mode": confirmed.value,
        "state_path": str(state_path),
        "set_to": mode.value,
    }, sort_keys=True))
    if confirmed != mode:  # pragma: no cover
        print(f"error: confirmation mismatch after write to {state_path}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
