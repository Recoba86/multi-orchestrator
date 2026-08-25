#!/usr/bin/env python3
"""Validate and display the user-editable role/model recommendations."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.model_policy import (
    ConfigurationError,
    PUBLIC_ROLES,
    ROLE_FIELDS,
    load_configuration,
    validate_configuration,
)
from core.model_discovery import DiscoveryResult, discover_codex_models
from core import model_intelligence
from core.model_capabilities import (
    assess_role_compatibility,
    capability_hints_for_role,
    lookup_model_capabilities,
)
from core.model_availability import (
    ErrorCategory,
    ModelAvailabilityRecord,
    ModelStatus,
    ProviderStatus,
    observe_model_offline,
    observe_provider_offline,
    probe_model_availability,
    probe_provider_health,
    sanitize_identifier,
)
from core.model_resolver import resolve_role, RoleResolution


ROLE_ORDER = PUBLIC_ROLES
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "models.yaml"
DEFAULT_INTELLIGENCE_CACHE_NAME = "model-intelligence.yaml"
MAX_DOCTOR_LINE_LENGTH = 512


def join_doctor_lines(lines: list[str] | tuple[str, ...]) -> str:
    """Join rendered lines, capping each line independently at MAX_DOCTOR_LINE_LENGTH with '...'."""
    capped: list[str] = []
    for line in lines:
        if len(line) > MAX_DOCTOR_LINE_LENGTH:
            capped.append(line[: MAX_DOCTOR_LINE_LENGTH - 3] + "...")
        else:
            capped.append(line)
    return chr(10).join(capped)


def _display_items(items: list[str]) -> str:
    # Keep a malformed multiline value from turning one configured field into
    # arbitrary output lines; validation still preserves the original value.
    return "; ".join(sanitize_identifier(" ".join(item.split())) for item in items)


def _display_exact(value: str) -> str:
    """Sanitize identifier for safe display without newline/control code injection."""
    return sanitize_identifier(value)


def render_model_availability(
    discovery: tuple[DiscoveryResult, ...],
    configuration: Mapping[str, Mapping[str, list[str]]],
    *,
    active_probes: bool = False,
) -> str:
    """Render model availability and provider health without inferring providers."""
    lines = [
        "Model availability and provider health (read-only; no network operations executed):"
    ]
    if active_probes:
        lines.append("Active probes mode: ENABLED (--active-probes requested).")
        lines.append(
            "No supported provider probe adapter exists; all probes report UNKNOWN/PROBE_UNSUPPORTED without network operations."
        )
    else:
        lines.append(
            "Active probes mode: DISABLED (default). Zero active probes executed."
        )

    lines.append(
        "Model availability is separate from declarations and capabilities. Declarations do not imply AVAILABLE."
    )
    lines.append(
        "Provider health is separate from model availability. Provider identity is explicit or UNKNOWN (no inference)."
    )

    lines.append("")
    lines.append("Provider health status:")
    provider_id = "UNKNOWN"
    if active_probes:
        p_record = probe_provider_health(provider_id)
    else:
        p_record = observe_provider_offline(provider_id)
    lines.append(
        f"  Provider {p_record.provider_id}: {p_record.status.value} ({p_record.provenance}) detail={p_record.detail}"
    )

    lines.append("")
    lines.append("Model availability status:")
    seen: set[str] = set()
    all_models: list[str] = []
    for role in ROLE_ORDER:
        for field in ("preferred", "fallback"):
            for model in configuration[role][field]:
                if model not in seen:
                    seen.add(model)
                    all_models.append(model)

    for result in discovery:
        if result.available:
            for model in result.models:
                if model not in seen:
                    seen.add(model)
                    all_models.append(model)

    if not all_models:
        lines.append("  none")
    else:
        for model in all_models:
            safe_model = sanitize_identifier(model)
            try:
                if active_probes:
                    m_record = probe_model_availability(model, provider_id="UNKNOWN")
                else:
                    m_record = observe_model_offline(model, provider_id="UNKNOWN")
                lines.append(
                    f"  Model {safe_model} (provider={m_record.provider_id}): {m_record.status.value} "
                    f"({m_record.provenance}) detail={m_record.detail}"
                )
            except (TypeError, ValueError):
                lines.append(
                    f"  Model {safe_model} (provider=UNKNOWN): UNKNOWN "
                    f"(offline-declaration) detail=invalid-identifier"
                )
    return join_doctor_lines(lines)


def render_configuration(configuration: Mapping[str, Mapping[str, list[str]]]) -> str:
    """Render validated values in the fixed public role order."""
    lines = [
        "Orchestrator Doctor",
        "Configuration: valid",
        "Values shown are recommendations/configuration only; discovery does not select models.",
    ]
    for role in ROLE_ORDER:
        entry = configuration[role]
        lines.extend(
            (
                "",
                f"Role: {role}",
                f"  Requires: {_display_items(entry['requires'])}",
                f"  Preferred models: {_display_items(entry['preferred'])}",
                f"  Fallback models: {_display_items(entry['fallback'])}",
                f"  Capability hints: {_display_items(entry['capability_hints'])}",
            )
        )
    return join_doctor_lines(lines)


def render_discovery(
    discovery: tuple[DiscoveryResult, ...],
    configuration: Mapping[str, Mapping[str, list[str]]],
) -> str:
    """Render discovery separately, then compare it with configured identifiers."""
    declared = {
        model for result in discovery if result.available for model in result.models
    }
    lines = ["Discovery (read-only declarations; no provider or runtime probing):"]
    for result in discovery:
        status = "AVAILABLE" if result.available else "UNAVAILABLE"
        lines.append(f"Discovery source {result.source}: {status} ({result.detail})")

    lines.append("Configured model comparison:")
    for role in ROLE_ORDER:
        lines.append(f"  Role: {role}")
        seen: set[str] = set()
        for field in ("preferred", "fallback"):
            for model in configuration[role][field]:
                if model in seen:
                    continue
                seen.add(model)
                declaration = "declared" if model in declared else "configured but not declared"
                lines.append(f"    {_display_exact(model)}: {declaration}")
    return join_doctor_lines(lines)


def render_capability_analysis(
    configuration: Mapping[str, Mapping[str, list[str]]],
) -> str:
    """Render descriptive capability metadata without selecting any model."""
    lines = [
        "Capability metadata and compatibility are advisory only.",
        "They do not prove provider health, authentication, entitlement, runtime availability, effective identity, authorization, or suitability.",
        "Built-in profiles are descriptive defaults; capability_hints remain user-owned advisory labels.",
        "Unknown model metadata is reported as UNKNOWN/metadata-unavailable, never as incompatible.",
    ]
    for role in ROLE_ORDER:
        hints = capability_hints_for_role(configuration, role)
        lines.extend(
            (
                "",
                f"Role: {role} capability analysis",
                f"  Advisory hints (config.{role}.capability_hints): {_display_items(list(hints))}",
            )
        )
        seen: set[str] = set()
        for field in ("preferred", "fallback"):
            for model in configuration[role][field]:
                if model in seen:
                    continue
                seen.add(model)
                metadata = lookup_model_capabilities(model)
                compatibility = assess_role_compatibility(model, hints)
                exact_model = _display_exact(model)
                lines.append(
                    f"  {exact_model}: {metadata.status}/{metadata.provenance}"
                )
                if metadata.status == "KNOWN":
                    lines.append(
                        f"    Capabilities: {', '.join(metadata.capabilities)}"
                    )
                else:
                    lines.append("    Capabilities: UNKNOWN")
                lines.append(f"    Provenance: {metadata.provenance}")
                if (
                    compatibility.status == "UNKNOWN"
                    and compatibility.detail == "metadata-unavailable"
                ):
                    lines.append("    Compatibility: UNKNOWN/metadata-unavailable")
                else:
                    lines.append(f"    Compatibility: {compatibility.status}")
    return join_doctor_lines(lines)


# Natural short name for callers that only need the rendered section.
render_capabilities = render_capability_analysis


def utc_now() -> datetime:
    """Return an aware UTC timestamp; callers may inject a fixed value in tests."""
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime:
    moment = utc_now() if value is None else value
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return moment.astimezone(timezone.utc)


def _cache_error_reason(error: Exception) -> str:
    """Map parser errors to a short reason without echoing cache contents."""
    text = str(error).lower()
    if "could not be read" in text or "unreadable" in text:
        return "could not be read"
    if "schema_version" in text or "schema" in text:
        return "invalid schema"
    if "evidence" in text:
        return "invalid evidence"
    if "claim" in text:
        return "invalid claim"
    if "identity" in text:
        return "invalid identity"
    if "root" in text or "mapping" in text or "requires" in text:
        return "invalid shape"
    return "invalid cache"


def _discovered_identities(discovery: tuple[DiscoveryResult, ...]) -> tuple[str, ...]:
    identities: list[str] = []
    seen: set[str] = set()
    for result in discovery:
        if not result.available:
            continue
        for model in result.models:
            if model in seen:
                continue
            seen.add(model)
            identities.append(model)
    return tuple(identities)


def _render_profile_claims(profile: model_intelligence.ModelProfile) -> list[str]:
    lines: list[str] = []
    if profile.conflicts:
        lines.append(f"    Conflicts: {', '.join(profile.conflicts)}")
    if not profile.claims:
        lines.append("    Claims: none")
        return lines
    for capability in sorted(profile.claims):
        claim = profile.claims[capability]
        strengths = sorted({record.strength for record in claim.evidence})
        provenance = sorted({record.source_type for record in claim.evidence})
        lines.append(
            "    "
            f"{capability}: score={claim.score} confidence={claim.confidence} "
            f"evidence_ids={','.join(claim.evidence_ids)} "
            f"strength={','.join(strengths) or 'UNKNOWN'} "
            f"provenance={','.join(provenance) or 'UNKNOWN'}"
        )
    return lines


def _normalized_for_display(raw_identity: str) -> str:
    try:
        return model_intelligence.normalize_identity(raw_identity)
    except ValueError:
        # Discovery accepts declarations that are later escaped for display;
        # keep the doctor usable even when lexical normalization rejects one.
        return raw_identity


def _load_intelligence_profiles(
    cache_path: Path, *, as_of: datetime
) -> tuple[str, str, tuple[model_intelligence.ModelProfile, ...]]:
    try:
        cache = model_intelligence.load_intelligence_cache(cache_path)
        profiles = model_intelligence.profiles_from_cache(cache, as_of=as_of)
    except Exception as error:
        if str(error) == "model intelligence cache not found":
            return "MISSING", "not found", ()
        return "INVALID", _cache_error_reason(error), ()
    return "VALID", "", profiles


def render_model_intelligence(
    discovery: tuple[DiscoveryResult, ...],
    configuration: Mapping[str, Mapping[str, list[str]]],
    cache_path: str | Path,
    *,
    as_of: datetime | None = None,
) -> str:
    """Render offline intelligence joined to exact discovered model strings."""
    del configuration  # Configuration remains authoritative and is rendered separately.
    moment = _as_utc(as_of)
    status, reason, profiles = _load_intelligence_profiles(
        Path(cache_path).expanduser(), as_of=moment
    )
    discovered = _discovered_identities(discovery)
    discovered_set = set(discovered)
    profile_by_raw = {profile.raw_identity: profile for profile in profiles}

    lines = [
        "Model intelligence (offline, read-only advisory; no provider or runtime probing):",
        f"Intelligence cache: {status}" + (f" ({reason})" if reason else ""),
        "Identity matching uses exact raw identities only. Normalization is not alias resolution; it is a lexical presentation (normalization is not alias resolution).",
        "Models.yaml preferred/fallback values remain authoritative; intelligence cannot select, route, or allocate models.",
        "Discovered identities:",
    ]
    if not discovered:
        lines.append("  none")
    for raw_identity in discovered:
        profile = profile_by_raw.get(raw_identity)
        lines.extend(
            (
                f"  Raw identity: {_display_exact(raw_identity)}",
                f"  Normalized identity: {_display_exact(_normalized_for_display(raw_identity))}",
                f"  Status: {profile.status if profile is not None else model_intelligence.STATUS_UNKNOWN}",
            )
        )
        if profile is not None:
            lines.extend(_render_profile_claims(profile))

    cache_only = sorted(
        (profile for profile in profiles if profile.raw_identity not in discovered_set),
        key=lambda profile: profile.raw_identity,
    )
    lines.append("Cache-only profiles (NOT_DISCOVERED; excluded from recommendations):")
    if not cache_only:
        lines.append("  none")
    for profile in cache_only:
        lines.extend(
            (
                f"  Raw identity: {_display_exact(profile.raw_identity)}",
                f"  Normalized identity: {_display_exact(profile.normalized_identity)}",
                "  Status: NOT_DISCOVERED",
                f"  Profile status: {profile.status}",
            )
        )
        lines.extend(_render_profile_claims(profile))

    if status != "VALID":
        lines.append(f"Advisory ranking withheld (cache {status}).")
        return join_doctor_lines(lines)

    active_discovered = [
        profile
        for raw_identity in discovered
        if (profile := profile_by_raw.get(raw_identity)) is not None
        and profile.status == model_intelligence.STATUS_ACTIVE
    ]
    lines.append(
        "Advisory recommendations (deterministic, non-selecting; discovered ACTIVE profiles only):"
    )
    for role in ROLE_ORDER:
        lines.append(f"  Role: {role}")
        recommendations = model_intelligence.recommend_roles(active_discovered, role)
        if not recommendations:
            lines.append("    none")
            continue
        for index, recommendation in enumerate(recommendations, start=1):
            lines.append(
                f"    {index}. raw={_display_exact(recommendation.raw_identity)} "
                f"score={recommendation.score:.2f} coverage={recommendation.coverage:.2f} "
                f"confidence={recommendation.confidence:.2f}"
            )
    return join_doctor_lines(lines)


def render_role_resolutions(
    configuration: Mapping[str, Mapping[str, list[str]]],
    discovery: tuple[DiscoveryResult, ...],
    cache_path: str | Path,
    *,
    as_of: datetime | None = None,
) -> str:
    """Render deterministic role resolutions via core.model_resolver.resolve_role."""
    moment = _as_utc(as_of)
    status, reason, profiles = _load_intelligence_profiles(
        Path(cache_path).expanduser(), as_of=moment
    )
    active_profiles = [
        p for p in profiles if p.status == model_intelligence.STATUS_ACTIVE
    ]

    lines = [
        "Role resolutions (deterministic evaluation via core.model_resolver):",
        "Evaluates exact configured candidates through hard constraints before advisory ranking.",
    ]

    for role in ROLE_ORDER:
        # Protect against overlong/malformed candidate strings in resolution
        try:
            resolution = resolve_role(
                configuration,
                role,
                discovery=discovery,
                profiles=active_profiles,
            )
        except Exception:
            resolution = None

        if resolution is None:
            lines.append(f"  Role {role}: outcome=UNKNOWN resolved_model=none")
            lines.append("    candidate=invalid-identifier outcome=UNRESOLVED reason=invalid-identifier score=none")
            continue

        resolved_display = (
            _display_exact(resolution.resolved_model)
            if resolution.resolved_model is not None
            else "none"
        )
        lines.append(
            f"  Role {role}: outcome={resolution.outcome} resolved_model={resolved_display}"
        )
        if not resolution.candidates:
            lines.append("    candidates: none")
        for candidate in resolution.candidates:
            raw_disp = _display_exact(candidate.raw_identity)
            score_disp = f"{candidate.weighted_score:.2f}" if candidate.weighted_score is not None else "none"
            lines.append(
                f"    candidate={raw_disp} outcome={candidate.outcome} "
                f"reason={candidate.reason} score={score_disp}"
            )

    return join_doctor_lines(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and display declarative Orchestrator role/model recommendations."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        type=Path,
        metavar="PATH",
        help="configuration YAML path (default: repository config/models.yaml)",
    )
    parser.add_argument(
        "--target-home",
        default=Path.home(),
        type=Path,
        metavar="PATH",
        help="home containing the Codex environment to inspect (default: current home)",
    )
    parser.add_argument(
        "--intelligence-cache",
        default=None,
        type=Path,
        metavar="PATH",
        help="offline model-intelligence cache (default: TARGET_HOME/.codex/model-intelligence.yaml)",
    )
    parser.add_argument(
        "--active-probes",
        action="store_true",
        default=False,
        help="request active provider/model availability probes (default: False; unsupported)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        configuration = load_configuration(args.config)
    except ConfigurationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    discovery = discover_codex_models(args.target_home)
    intelligence_cache = (
        args.intelligence_cache
        if args.intelligence_cache is not None
        else args.target_home.expanduser() / ".codex" / DEFAULT_INTELLIGENCE_CACHE_NAME
    )
    print(render_configuration(configuration))
    print()
    print(render_discovery(discovery, configuration))
    print()
    print(render_capability_analysis(configuration))
    print()
    print(render_model_availability(discovery, configuration, active_probes=args.active_probes))
    print()
    print(
        render_model_intelligence(
            discovery,
            configuration,
            intelligence_cache,
            as_of=utc_now(),
        )
    )
    print()
    print(
        render_role_resolutions(
            configuration,
            discovery,
            intelligence_cache,
            as_of=utc_now(),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
