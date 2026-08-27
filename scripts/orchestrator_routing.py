#!/usr/bin/env python3
"""Unified Operator CLI for Multi-Orchestrator runtime routing (Task 12).

Commands:
    orchestrator-routing status
    orchestrator-routing on
    orchestrator-routing off
    orchestrator-routing mode SolMode|GrokMode
    orchestrator-routing use SolMode|GrokMode
    orchestrator-routing validate [--config-path PATH]
    orchestrator-routing models [--config-path PATH]
    orchestrator-routing report [--telemetry-path PATH] [--window-hours N]

Exit codes:
    0: Success
    1: Runtime/Validation failure
    2: Argument error
"""

from __future__ import annotations

import argparse
from datetime import timedelta
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_endpoint_validator import RuntimeEndpointValidator
from core.runtime_routing_mode import (
    GROK_MODE,
    MODE_STATE_PATH_DEFAULT,
    SOL_MODE,
    RoutingMode,
    read_mode,
    write_mode,
)
from core.runtime_routing_switch import (
    ROUTING_SWITCH_PATH_DEFAULT,
    is_routing_enabled,
    set_routing_enabled,
)
from core.runtime_routing_policy import (
    load_runtime_policy,
)
from core.runtime_routing_health import (
    HEALTH_STATE_PATH_DEFAULT,
    excluded_domains,
    excluded_endpoints,
)
from core.runtime_routing_telemetry import (
    TELEMETRY_PATH_DEFAULT,
    aggregate_telemetry,
)

DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrator-routing",
        description="Unified operator CLI for Multi-Orchestrator runtime routing management.",
    )
    parser.add_argument(
        "--state-path",
        type=Path,
        default=MODE_STATE_PATH_DEFAULT,
        help="Path to authoritative mode.json (default: %(default)s)",
    )
    parser.add_argument(
        "--switch-path",
        type=Path,
        default=ROUTING_SWITCH_PATH_DEFAULT,
        help="Path to master switch enabled.json (default: %(default)s)",
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
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to runtime-routing.yaml (default: %(default)s)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # status
    sub.add_parser("status", help="Show master switch, active mode, health, and config path.")

    # on / off
    sub.add_parser("on", help="Enable runtime mode-aware routing.")
    sub.add_parser("off", help="Disable runtime routing (restore legacy authority).")

    # mode
    mode_parser = sub.add_parser("mode", help="Change persistent mode without toggling enabled state.")
    mode_parser.add_argument(
        "mode",
        choices=["SolMode", "GrokMode"],
        help="Target routing mode (SolMode | GrokMode)",
    )

    # use
    use_parser = sub.add_parser("use", help="Set persistent mode and enable runtime routing.")
    use_parser.add_argument(
        "mode",
        choices=["SolMode", "GrokMode"],
        help="Target routing mode to activate (SolMode | GrokMode)",
    )

    # validate
    sub.add_parser("validate", help="Statically validate active runtime routing configuration.")

    # models
    sub.add_parser("models", help="Display declarative runtime endpoint catalog.")

    # report
    report_parser = sub.add_parser("report", help="Display target-share observation report.")
    report_parser.add_argument(
        "--window-hours",
        type=float,
        help="Rolling time window in hours to filter events (default: all events)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "on":
        set_routing_enabled(True, path=args.switch_path)
        current_mode = read_mode(args.state_path)
        print(f"[OK] Runtime routing ENABLED (Master Switch: ON, Mode: {current_mode.value})")
        return 0

    if args.command == "off":
        set_routing_enabled(False, path=args.switch_path)
        current_mode = read_mode(args.state_path)
        print(f"[OK] Runtime routing DISABLED (Master Switch: OFF / Legacy Authority, Mode: {current_mode.value})")
        return 0

    if args.command == "mode":
        target_mode = SOL_MODE if args.mode == "SolMode" else GROK_MODE
        write_mode(target_mode, state_path=args.state_path)
        enabled = is_routing_enabled(args.switch_path)
        print(f"[OK] Persistent mode set to {target_mode.value} (Master Switch: {'ON' if enabled else 'OFF'})")
        return 0

    if args.command == "use":
        target_mode = SOL_MODE if args.mode == "SolMode" else GROK_MODE
        write_mode(target_mode, state_path=args.state_path)
        set_routing_enabled(True, path=args.switch_path)
        print(f"[OK] Persistent mode set to {target_mode.value} and runtime routing ENABLED (Master Switch: ON)")
        return 0

    if args.command == "validate":
        try:
            policy = load_runtime_policy(args.config_path)
            endpoint_val = RuntimeEndpointValidator(runtime_policy=policy)
            ok, err = endpoint_val.validate_catalog_conflicts()
            if not ok:
                print(f"[FAIL] Configuration validation error: {err}", file=sys.stderr)
                return 1
            print(f"[PASS] Runtime routing configuration at {args.config_path} is VALID.")
            return 0
        except Exception as exc:
            print(f"[FAIL] Configuration validation error: {exc}", file=sys.stderr)
            return 1

    if args.command == "models":
        try:
            policy = load_runtime_policy(args.config_path)
            print(f"=== Declarative Runtime Endpoint Catalog ({args.config_path}) ===")
            print(f"{'Endpoint ID':<20} {'Model':<45} {'Effort':<8} {'Enabled':<8} {'Verified':<9} {'Domain':<12} {'Group':<12}")
            print("-" * 120)
            for ep_id, meta in sorted(policy.endpoint_resolution.items()):
                dom = next((d for d, obj in policy.domains.items() if ep_id in obj.endpoint_ids), "unknown")
                grp = next((g for g, eps in policy.independence_groups.items() if ep_id in eps), "unknown")
                en_str = str(meta.get("enabled", True))
                ver_str = str(meta.get("verified", False))
                print(f"{ep_id:<20} {meta.get('model',''):<45} {meta.get('effort',''):<8} {en_str:<8} {ver_str:<9} {dom:<12} {grp:<12}")
            return 0
        except Exception as exc:
            print(f"[FAIL] Error loading models catalog: {exc}", file=sys.stderr)
            return 1

    if args.command == "report":
        try:
            policy = load_runtime_policy(args.config_path)
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
            return 0
        except Exception as exc:
            print(f"[FAIL] Error generating report: {exc}", file=sys.stderr)
            return 1

    if args.command == "status":
        enabled = is_routing_enabled(args.switch_path)
        mode = read_mode(args.state_path)
        unhealthy_doms = excluded_domains(path=args.health_path)
        try:
            policy = load_runtime_policy(args.config_path)
            config_status = "VALID"
            total_models = len(policy.endpoint_resolution)
            active_eps = [
                ep for ep, m in sorted(policy.endpoint_resolution.items())
                if m.get("enabled", True) and m.get("verified", False) and m.get("eligibility") == "eligible"
            ]
            disabled_eps = [
                ep for ep, m in sorted(policy.endpoint_resolution.items())
                if not m.get("enabled", True) or m.get("eligibility") == "disabled"
            ]
            fail_closed_eps = [
                ep for ep, m in sorted(policy.endpoint_resolution.items())
                if not m.get("verified", False) or m.get("eligibility") == "unverified"
            ]
        except Exception:
            config_status = "INVALID"
            total_models = 0
            active_eps = []
            disabled_eps = []
            fail_closed_eps = []

        print("=== Multi-Orchestrator Routing Status ===")
        print(f"Master Switch:       {'ON (Mode-Aware Routing Active)' if enabled else 'OFF (Legacy Wrapper Authority Active)'}")
        print(f"Persistent Mode:     {mode.value}")
        print(f"Active Config Path:  {args.config_path} ({config_status}, {total_models} endpoints declared)")
        print(f"Active Endpoints:    {', '.join(active_eps) if active_eps else 'None'}")
        print(f"Disabled Endpoints:  {', '.join(disabled_eps) if disabled_eps else 'None'}")
        print(f"Fail-Closed/Unver:   {', '.join(fail_closed_eps) if fail_closed_eps else 'None'}")
        print(f"Health Cooldowns:    {', '.join(unhealthy_doms) if unhealthy_doms else 'None (All domains healthy)'}")
        print(f"State Path:          {args.state_path}")
        print(f"Switch Path:         {args.switch_path}")
        print(f"Telemetry Path:      {args.telemetry_path}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
