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


class _CustomArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.stderr.write(f"See '{self.prog} --help' for available commands and usage.\n")
        sys.exit(2)


def build_parser() -> argparse.ArgumentParser:
    epilog_text = """Commands & Usage:
  status                      Show master switch, active mode, health, active/disabled/unverified endpoints
  on                          Enable runtime mode-aware routing
  off                         Disable runtime routing (restore legacy wrapper authority, preserve mode)
  mode <SolMode|GrokMode>     Change persistent mode (without toggling master switch)
  use <SolMode|GrokMode>      Set persistent mode AND enable runtime routing
  models                      Display declarative runtime endpoint catalog
  validate                    Statically validate active runtime routing configuration
  report                      Display observed telemetry share report
  help [command]              Show top-level or command-specific help

Quick examples:
  Turn routing off:           orchestrator-routing off
  Enable SolMode:             orchestrator-routing use SolMode
  Enable GrokMode:            orchestrator-routing use GrokMode
  Check everything:           orchestrator-routing status
  After editing models:       orchestrator-routing validate
"""
    parser = _CustomArgumentParser(
        prog="orchestrator-routing",
        description="orchestrator-routing — Unified Operator CLI for Multi-Orchestrator Runtime Routing Control.",
        epilog=epilog_text,
        formatter_class=argparse.RawDescriptionHelpFormatter,
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

    sub = parser.add_subparsers(dest="command", required=False)

    # status
    sub.add_parser(
        "status",
        help="Show master switch, active mode, health cooldowns, endpoint catalog status, and quick actions.",
        description="Show master switch, active mode, health cooldowns, endpoint catalog status, and quick actions.",
    )

    # on / off
    sub.add_parser(
        "on",
        help="Enable runtime mode-aware routing (uses currently persisted mode).",
        description="Enable runtime mode-aware routing. Uses the currently persisted SolMode/GrokMode without automatically modifying the mode.",
    )
    sub.add_parser(
        "off",
        help="Disable runtime routing (soft rollback to legacy wrapper authority; preserves mode and health state).",
        description="Disable runtime mode-aware routing and immediately restore legacy wrapper routing authority. Preserves currently persisted mode and health cooldown state.",
    )

    # mode
    mode_parser = sub.add_parser(
        "mode",
        help="Change persistent mode without toggling master ON/OFF state.",
        description="Change persistent mode (SolMode or GrokMode). Does NOT modify master ON/OFF switch state.",
    )
    mode_parser.add_argument(
        "mode",
        choices=["SolMode", "GrokMode"],
        help="Target routing mode (SolMode | GrokMode)",
    )

    # use
    use_parser = sub.add_parser(
        "use",
        help="Convenience action: set persistent mode AND enable runtime routing.",
        description="Convenience action: sets the requested persistent mode (SolMode or GrokMode) AND explicitly enables runtime mode-aware routing.",
    )
    use_parser.add_argument(
        "mode",
        choices=["SolMode", "GrokMode"],
        help="Target routing mode to activate (SolMode | GrokMode)",
    )

    # validate
    sub.add_parser(
        "validate",
        help="Statically validate active runtime routing configuration against schemas and Core rules.",
        description="Statically validate active runtime routing configuration against schemas, domain definitions, effort rules, and Core endpoint conflict rules. Performs zero routing-state mutation.",
    )

    # models
    sub.add_parser(
        "models",
        help="Display declarative runtime endpoint catalog (enabled/disabled/verified status).",
        description="Display declarative runtime endpoint catalog including enabled, disabled, verified, and fail-closed status.",
    )

    # report
    report_parser = sub.add_parser(
        "report",
        help="Display observed telemetry / dispatch share report (telemetry does not control selection).",
        description="Display observed telemetry / dispatch share report across permanent target domains and opportunistic overlays. Telemetry is observation-only and does not control routing decisions.",
    )
    report_parser.add_argument(
        "--window-hours",
        type=float,
        help="Rolling time window in hours to filter events (default: all events)",
    )

    # help
    help_parser = sub.add_parser(
        "help",
        help="Display top-level or command-specific help.",
        description="Display top-level or command-specific help.",
    )
    help_parser.add_argument(
        "target_command",
        nargs="?",
        help="Optional command name to view specific help for (e.g. status, on, off, mode, use, models, validate, report)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "help":
        if args.target_command:
            subparsers_action = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
            if subparsers_action and args.target_command in subparsers_action.choices:
                subparsers_action.choices[args.target_command].print_help()
                return 0
            print(f"Unknown command: '{args.target_command}'. See 'orchestrator-routing --help'.", file=sys.stderr)
            return 2
        parser.print_help()
        return 0
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
        print("\nQuick actions:")
        print("  Disable routing : orchestrator-routing off")
        print("  Enable routing  : orchestrator-routing on")
        print("  Use SolMode     : orchestrator-routing use SolMode")
        print("  Use GrokMode    : orchestrator-routing use GrokMode")
        print("  Models          : orchestrator-routing models")
        print("  Full help       : orchestrator-routing --help")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
