#!/usr/bin/env python3
"""Inspect and safely configure logical model role preferences."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.model_policy import (
    ConfigurationError,
    PUBLIC_ROLES,
    apply_role_selections,
    compute_file_sha256,
    is_public_role,
    load_configuration,
    mutate_configuration_file,
    validate_configuration,
)
from core.model_discovery import discover_codex_models
from core.model_availability import sanitize_identifier


DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "models.yaml"


def parse_assignment(arg: str) -> tuple[str, str]:
    """Parse ROLE=MODEL assignment."""
    if "=" not in arg:
        raise ConfigurationError(f"invalid assignment '{arg}', expected ROLE=MODEL")
    role, model = arg.split("=", 1)
    role = role.strip()
    model = model.strip()
    if not is_public_role(role):
        raise ConfigurationError(f"unknown role '{role}', must be one of {', '.join(PUBLIC_ROLES)}")
    if not model:
        raise ConfigurationError(f"model for role '{role}' cannot be empty")
    return role, model


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect and safely configure declarative role preferences."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        type=Path,
        metavar="PATH",
        help="configuration YAML path (default: repository config/models.yaml)",
    )
    parser.add_argument(
        "--set",
        dest="assignments",
        action="append",
        metavar="ROLE=MODEL",
        help="assign a model to a role's preferred top spot (e.g. planner=gpt-5.6-sol)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="perform safe atomic mutation (default is dry-run)",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        default=False,
        help="explicit approval flag required when --apply is set",
    )
    parser.add_argument(
        "--expected-sha256",
        metavar="HEX",
        help="expected SHA-256 hash of the configuration file before mutation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config_path = args.config.expanduser()
        current_sha256 = compute_file_sha256(config_path)
        configuration = load_configuration(config_path)

        if not args.assignments:
            print(f"Configuration file: {config_path}")
            print(f"Current SHA-256: {current_sha256}")
            print("Current preferred roles:")
            for role in PUBLIC_ROLES:
                preferred = configuration[role]["preferred"]
                print(f"  {role}: {preferred[0] if preferred else 'none'}")
            return 0

        selections: dict[str, str] = {}
        for item in args.assignments:
            role, model = parse_assignment(item)
            if role in selections:
                raise ConfigurationError(f"duplicate assignment for role '{role}'")
            selections[role] = model

        if not args.apply:
            # Dry run
            result = mutate_configuration_file(
                config_path,
                selections,
                expected_sha256=args.expected_sha256,
                dry_run=True,
            )
            print("DRY RUN (no changes written):")
            print(f"  Target: {config_path}")
            print(f"  Current SHA-256: {result.before_sha256}")
            print(f"  Projected SHA-256: {result.after_sha256}")
            print("  Projected preferred models:")
            for role, model in selections.items():
                print(f"    {role} -> {model}")
            return 0

        # Apply mutation
        if not args.approve:
            raise ConfigurationError("mutation requires explicit --approve flag")
        if not args.expected_sha256:
            raise ConfigurationError("mutation requires explicit --expected-sha256")

        result = mutate_configuration_file(
            config_path,
            selections,
            expected_sha256=args.expected_sha256,
            dry_run=False,
            approved=args.approve,
        )
        print("Configuration applied successfully:")
        print(f"  Target: {result.config_path}")
        print(f"  Before SHA-256: {result.before_sha256}")
        print(f"  After SHA-256:  {result.after_sha256}")
        print(f"  Backup: {result.backup_path}")
        print("  Updated preferred models:")
        for role, model in selections.items():
            print(f"    {role} -> {model}")
        return 0

    except ConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
