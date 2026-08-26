#!/usr/bin/env python3
"""Shadow Controller CLI for model routing and target-share reporting (Task 9).

Usage:
    route_model.py select --role ROLE [--mission-id M] [--ordinal N] [--implementer IMP]
                          [--state-path P] [--health-path H] [--telemetry-path T] [--no-telemetry]
    route_model.py report [--window-hours N] [--telemetry-path T]

Exit codes:
    0: Success
    1: Routing error / No eligible candidate
    2: Invalid CLI arguments
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_boss_binding import shadow_boss_binding
from core.runtime_reviewer_selector import select_reviewer
from core.runtime_role_dispatch import dispatch_role
from core.runtime_routing_policy import (
    group_of,
    load_runtime_policy,
)
from core.runtime_routing_health import (
    HEALTH_STATE_PATH_DEFAULT,
    domain_eligible,
    excluded_endpoints,
)
from core.runtime_routing_mode import (
    MODE_STATE_PATH_DEFAULT,
    read_mode,
)
from core.runtime_routing_telemetry import (
    TELEMETRY_PATH_DEFAULT,
    RoutingEvent,
    aggregate_telemetry,
    append_routing_event,
)
from core.runtime_weighted_selector import SelectionKey

DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="route_model.py",
        description="Shadow Controller CLI for model routing and target-share reporting.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=MODE_STATE_PATH_DEFAULT,
        help="Path to authoritative mode.json (default: %(default)s)",
    )
    parser.add_argument(
        "--health-path",
        type=Path,
        default=HEALTH_STATE_PATH_DEFAULT,
        help="Path to health state JSON (default: %(default)s)",
    )
    parser.add_argument(
        "--telemetry-path",
        type=Path,
        default=TELEMETRY_PATH_DEFAULT,
        help="Path to telemetry JSONL log (default: %(default)s)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # SELECT subcommand
    select_parser = sub.add_parser("select", help="Compute shadow routing decision for a role.")
    select_parser.add_argument(
        "--role",
        required=True,
        choices=["BOSS", "SCOUT", "STANDARD_WORKER", "DEEP_WORKER", "VERIFIER"],
        help="Logical role to select for",
    )
    select_parser.add_argument(
        "--mission-id",
        default="cli-mission",
        help="Mission identifier (default: %(default)s)",
    )
    select_parser.add_argument(
        "--ordinal",
        type=int,
        default=0,
        help="Dispatch ordinal (default: 0)",
    )
    select_parser.add_argument(
        "--implementer",
        help="Implementer endpoint ID (required for VERIFIER role)",
    )
    select_parser.add_argument(
        "--now",
        type=int,
        help="Explicit integer epoch timestamp (default: current time)",
    )
    select_parser.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Do not record telemetry for this selection",
    )

    # REPORT subcommand
    report_parser = sub.add_parser("report", help="Display target-share observation report.")
    report_parser.add_argument(
        "--window-hours",
        type=float,
        help="Rolling time window in hours to filter events (default: all events)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    policy = load_runtime_policy(DEFAULT_POLICY_PATH)
    validator = PolicyValidator()

    if args.command == "report":
        window = timedelta(hours=args.window_hours) if args.window_hours else None
        report = aggregate_telemetry(path=args.telemetry_path, policy=policy, window=window)

        print("=== Permanent Target Domains ===")
        print(f"{'Domain':<15} {'Target %':<10} {'Observed %':<12} {'Delta %':<10} {'Count':<8}")
        print("-" * 55)
        for dom, stats in report.domain_shares.items():
            print(f"{dom:<15} {stats['target_pct']:<10.1f} {stats['observed_pct']:<12.1f} {stats['delta_pct']:<+10.1f} {stats['count']:<8}")

        print("\n=== Opportunistic Overlay (OX) ===")
        print(f"ox_combo count: {report.ox_stats['count']}")
        print(f"ox_combo share of all dispatches: {report.ox_stats['share_of_all_dispatches_pct']:.1f}%")
        print(f"\nTotal permanent dispatches: {report.total_permanent_dispatches}")
        print(f"Total all dispatches: {report.total_all_dispatches}")
        if report.malformed_rows_count > 0:
            print(f"Malformed records ignored: {report.malformed_rows_count}")
        return 0

    if args.command == "select":
        mode = read_mode(args.state_path)
        now_ts = args.now if args.now is not None else int(datetime.now().timestamp())
        now_iso = datetime.now(timezone.utc).isoformat()

        def _is_domain_eligible(dom: str) -> bool:
            return domain_eligible(dom, now=now_ts, path=args.health_path, policy=policy)

        health_excl = excluded_endpoints(policy, now=now_ts, path=args.health_path)

        if args.role == "BOSS":
            dec = shadow_boss_binding(
                mode=mode,
                policy=policy,
                domain_eligible=_is_domain_eligible,
                validator=validator,
            )
            event = RoutingEvent(
                timestamp_utc=now_iso,
                mode=mode.value,
                role="BOSS",
                endpoint_id=dec.selected_endpoint,
                endpoint_independence_group=group_of(policy, dec.selected_endpoint),
                capacity_domain=dec.failure_domain,
                model=dec.model,
                effort=dec.effort,
                core_validation_status=dec.core_validation_status,
                table_used="boss_chain",
                mission_id=args.mission_id,
                ordinal=args.ordinal,
                bucket=None,
                algorithm_version=1,
                excluded_unverified=(),
                implementer_independence_group=None,
                decision_reason=dec.decision_reason,
            )
            output = {
                "role": "BOSS",
                "mode": mode.value,
                "selected_endpoint": dec.selected_endpoint,
                "model": dec.model,
                "effort": dec.effort,
                "failure_domain": dec.failure_domain,
                "core_validation_status": dec.core_validation_status,
                "continuity_status": dec.continuity_status,
            }

        elif args.role in ("SCOUT", "STANDARD_WORKER", "DEEP_WORKER"):
            key = SelectionKey(
                mission_id=args.mission_id,
                role=args.role,
                ordinal=args.ordinal,
                mode=mode,
            )
            dec = dispatch_role(
                policy=policy,
                role=args.role,
                key=key,
                excluded_endpoints=health_excl,
                validator=validator,
                domain_eligible=_is_domain_eligible,
            )
            event = RoutingEvent(
                timestamp_utc=now_iso,
                mode=mode.value,
                role=args.role,
                endpoint_id=dec.selected_endpoint,
                endpoint_independence_group=dec.independence_group,
                capacity_domain=dec.failure_domain,
                model=dec.model,
                effort=dec.effort,
                core_validation_status=dec.core_validation_status,
                table_used=dec.table_used,
                mission_id=args.mission_id,
                ordinal=args.ordinal,
                bucket=dec.selection_evidence.bucket,
                algorithm_version=dec.selection_evidence.algorithm_version,
                excluded_unverified=dec.excluded_unverified,
                implementer_independence_group=None,
                decision_reason="Role dispatch selected candidate",
            )
            output = {
                "role": args.role,
                "mode": mode.value,
                "selected_endpoint": dec.selected_endpoint,
                "model": dec.model,
                "effort": dec.effort,
                "failure_domain": dec.failure_domain,
                "independence_group": dec.independence_group,
                "table_used": dec.table_used,
                "core_validation_status": dec.core_validation_status,
                "bucket": dec.selection_evidence.bucket,
            }

        elif args.role == "VERIFIER":
            if not args.implementer:
                print("error: --implementer is required for VERIFIER role", file=sys.stderr)
                return 2

            key = SelectionKey(
                mission_id=args.mission_id,
                role="VERIFIER",
                ordinal=args.ordinal,
                mode=mode,
            )
            dec = select_reviewer(
                policy=policy,
                implementer_endpoint=args.implementer,
                key=key,
                excluded_endpoints=health_excl,
                validator=validator,
                domain_eligible=_is_domain_eligible,
            )
            event = RoutingEvent(
                timestamp_utc=now_iso,
                mode=mode.value,
                role="VERIFIER",
                endpoint_id=dec.selected_endpoint,
                endpoint_independence_group=dec.selected_independence_group,
                capacity_domain=dec.selected_failure_domain,
                model=dec.selected_model,
                effort=dec.selected_effort,
                core_validation_status=dec.core_validation_status,
                table_used="reviewer_table",
                mission_id=args.mission_id,
                ordinal=args.ordinal,
                bucket=dec.selection_evidence.bucket,
                algorithm_version=dec.selection_evidence.algorithm_version,
                excluded_unverified=(),
                implementer_independence_group=dec.implementer_independence_group,
                decision_reason=dec.decision_reason,
            )
            output = {
                "role": "VERIFIER",
                "mode": mode.value,
                "implementer_endpoint": dec.implementer_endpoint,
                "implementer_independence_group": dec.implementer_independence_group,
                "selected_endpoint": dec.selected_endpoint,
                "model": dec.selected_model,
                "effort": dec.selected_effort,
                "failure_domain": dec.selected_failure_domain,
                "independence_group": dec.selected_independence_group,
                "core_validation_status": dec.core_validation_status,
                "bucket": dec.selection_evidence.bucket,
            }

        # Print JSON output
        print(json.dumps(output, sort_keys=True))

        # Append telemetry unless opted out
        if not args.no_telemetry:
            try:
                append_routing_event(event, path=args.telemetry_path)
            except Exception as exc:
                print(f"warning: telemetry append failed: {exc}", file=sys.stderr)

        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
