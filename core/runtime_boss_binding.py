"""Shadow Boss mode eligibility and binding computation (Task 4).

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§2.2, §2.3, §2.4)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 4)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Collection, Optional

from core.policy_validator import PolicyValidator
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import (
    RuntimePolicy,
    boss_chain_for,
    load_runtime_policy,
)

__all__ = [
    "NoEligibleBossError",
    "ShadowBossDecision",
    "shadow_boss_binding",
    "legacy_binding",
    "MODE_EXCLUDED_GPT_PLUS",
    "HEALTH_COOLDOWN",
    "REASON_STATIC_INELIGIBLE",
    "REASON_TEMPORARY_EXCLUSION",
    "REASON_NEW_MISSION_BINDING",
    "CONTINUE_EXISTING_BOSS",
]

MODE_EXCLUDED_GPT_PLUS = "MODE_EXCLUDED_GPT_PLUS"
HEALTH_COOLDOWN = "HEALTH_COOLDOWN"
REASON_STATIC_INELIGIBLE = "STATIC_INELIGIBLE"
REASON_TEMPORARY_EXCLUSION = "TEMPORARY_EXCLUSION"
REASON_NEW_MISSION_BINDING = "NEW_MISSION_BINDING"
CONTINUE_EXISTING_BOSS = "CONTINUE_EXISTING_BOSS"

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "runtime-routing.yaml"

_LEGACY_BINDINGS = {
    "sol-luna-orchestrator-v2": "SOL_HIGH",
    "grok-orchestrator-v2": "GROK_4_6_HIGH",
}


class NoEligibleBossError(RuntimeError):
    """Raised when priority chain contains zero eligible Boss candidates."""
    pass


@dataclass(frozen=True)
class ShadowBossDecision:
    """Immutable decision evidence for Boss binding in shadow mode."""
    mode: RoutingMode
    chain: tuple[str, ...]
    selected_endpoint: str
    model: str
    effort: str
    failure_domain: str
    excluded_endpoints: tuple[tuple[str, str], ...]
    core_validation_status: str
    decision_reason: str
    continuity_status: str


def legacy_binding(skill_name: str) -> str:
    """Map legacy skill wrapper names to their fixed Boss endpoint bindings."""
    if skill_name in _LEGACY_BINDINGS:
        return _LEGACY_BINDINGS[skill_name]
    raise ValueError(f"unknown skill wrapper name {skill_name!r}")


def _domain_of(policy: RuntimePolicy, endpoint_id: str) -> str:
    """Resolve the capacity/failure domain name for an endpoint."""
    for dom_name, domain_obj in policy.domains.items():
        if endpoint_id in domain_obj.endpoint_ids:
            return dom_name
    return "unknown"


def shadow_boss_binding(
    mode: RoutingMode,
    policy: Optional[RuntimePolicy] = None,
    domain_eligible: Optional[Callable[[str], bool]] = None,
    excluded_endpoints: Optional[Collection[str]] = None,
    existing_mission_boss: Optional[str] = None,
    validator: Optional[PolicyValidator] = None,
) -> ShadowBossDecision:
    """Compute shadow-mode Boss binding decision without spawning or mutating state.

    Walks the mode-specific priority chain in strict order.
    The first candidate that passes static policy eligibility, domain health,
    and explicit exclusions is selected.

    If `existing_mission_boss` is supplied and valid, preserves Boss continuity
    regardless of mode changes.
    """
    if not isinstance(mode, RoutingMode):
        raise ValueError(f"mode must be a RoutingMode instance, got {mode!r}")

    if policy is None:
        policy = load_runtime_policy(_DEFAULT_CONFIG_PATH)

    chain = boss_chain_for(policy, mode)
    explicit_exclusions = set(excluded_endpoints or ())
    gpt_plus_endpoints = set(policy.domains.get("gpt_plus", None).endpoint_ids if "gpt_plus" in policy.domains else ())

    if validator is None:
        validator = PolicyValidator()

    # 1. Boss continuity check
    if existing_mission_boss:
        if existing_mission_boss in policy.endpoint_resolution:
            meta = policy.endpoint_resolution[existing_mission_boss]
            model = meta.get("model", "")
            effort = meta.get("effort", "")
            dom = _domain_of(policy, existing_mission_boss)

            # Core validation check
            core_ok, core_err = validator.validate_requested_endpoint(existing_mission_boss)
            if core_ok:
                eff_ok, eff_err = validator.validate_endpoint_effort(existing_mission_boss, effort)
                core_status = "REQUEST_VALID" if eff_ok else f"INVALID_EFFORT: {eff_err}"
            else:
                core_status = f"CORE_ENDPOINT_INVALID: {core_err}"

            return ShadowBossDecision(
                mode=mode,
                chain=chain,
                selected_endpoint=existing_mission_boss,
                model=model,
                effort=effort,
                failure_domain=dom,
                excluded_endpoints=(),
                core_validation_status=core_status,
                decision_reason="Preserved existing mission Boss continuity",
                continuity_status=CONTINUE_EXISTING_BOSS,
            )

    # 2. Priority chain walk
    exclusions_recorded: list[tuple[str, str]] = []
    selected: Optional[str] = None

    for ep in chain:
        # Check GrokMode GPT-plus exclusion defense
        if mode == GROK_MODE and ep in gpt_plus_endpoints:
            exclusions_recorded.append((ep, MODE_EXCLUDED_GPT_PLUS))
            continue

        # Check explicit temporary exclusions
        if ep in explicit_exclusions:
            exclusions_recorded.append((ep, REASON_TEMPORARY_EXCLUSION))
            continue

        # Check static policy eligibility
        meta = policy.endpoint_resolution.get(ep)
        if not meta or not meta.get("verified", False) or meta.get("eligibility") != "eligible":
            exclusions_recorded.append((ep, REASON_STATIC_INELIGIBLE))
            continue

        # Check dynamic domain health/cooldown if callable provided
        dom = _domain_of(policy, ep)
        if domain_eligible is not None:
            if not domain_eligible(dom):
                exclusions_recorded.append((ep, HEALTH_COOLDOWN))
                continue

        selected = ep
        break

    if selected is None:
        raise NoEligibleBossError(
            f"No eligible Boss candidate found in priority chain for {mode.value}. "
            f"Chain: {chain}, Exclusions: {exclusions_recorded}"
        )

    res = policy.endpoint_resolution[selected]
    model = res.get("model", "")
    effort = res.get("effort", "")
    dom = _domain_of(policy, selected)

    # Core PolicyValidator verification
    core_ok, core_err = validator.validate_requested_endpoint(selected)
    if core_ok:
        eff_ok, eff_err = validator.validate_endpoint_effort(selected, effort)
        core_status = "REQUEST_VALID" if eff_ok else f"INVALID_EFFORT: {eff_err}"
    else:
        core_status = f"CORE_ENDPOINT_INVALID: {core_err}"

    return ShadowBossDecision(
        mode=mode,
        chain=chain,
        selected_endpoint=selected,
        model=model,
        effort=effort,
        failure_domain=dom,
        excluded_endpoints=tuple(exclusions_recorded),
        core_validation_status=core_status,
        decision_reason=f"Selected first eligible candidate in {mode.value} chain",
        continuity_status=REASON_NEW_MISSION_BINDING,
    )
