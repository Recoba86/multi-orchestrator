#!/usr/bin/env python3
"""Manual SolMode/GrokMode operator CLI (plan Task 1).

The ONLY writer of persistent routing mode is the explicit ``set``
subcommand issued by an operator. ``status`` is strictly read-only.

Usage:
    orchestrator_mode.py status
    orchestrator_mode.py set sol|grok
    orchestrator_mode.py ... --state-path PATH

Exit codes: 0 success; 2 invalid arguments (no state mutation).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.runtime_routing_mode import (  # noqa: E402
    MODE_STATE_PATH_DEFAULT,
    GROK_MODE,
    SOL_MODE,
    read_mode,
    write_mode,
)

_SET_CHOICES = {"sol": SOL_MODE, "grok": GROK_MODE}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrator-mode",
        description="View or manually set persistent SolMode/GrokMode state.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=MODE_STATE_PATH_DEFAULT,
        help="authoritative mode.json path (default: %(default)s)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="print current mode; read-only")

    set_parser = sub.add_parser("set", help="persist a mode explicitly")
    set_parser.add_argument(
        "mode",
        choices=sorted(_SET_CHOICES),
        help="sol = SolMode (gpt_plus eligible), grok = GrokMode (excluded)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    state_path: Path = args.state_path

    if args.command == "status":
        mode = read_mode(state_path)  # read-only by contract
        print(json.dumps({
            "mode": mode.value,
            "state_path": str(state_path),
            "source": "persisted" if state_path.exists() else "default",
        }, sort_keys=True))
        return 0

    # set: explicit, validated, atomic write; confirm resulting state.
    mode = _SET_CHOICES[args.mode]
    write_mode(mode, state_path)
    confirmed = read_mode(state_path)
    print(json.dumps({
        "mode": confirmed.value,
        "state_path": str(state_path),
        "set_to": mode.value,
    }, sort_keys=True))
    if confirmed != mode:  # pragma: no cover - replace() failure surface
        print(f"error: confirmation mismatch after write to {state_path}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
