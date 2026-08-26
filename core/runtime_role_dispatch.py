"""Shadow Scout, Standard Worker, and Deep Worker dispatch facade (Task 5).

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§5.1, §5.2, §5.3, §5.5a, §5.6, §5.7, §13.1)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 5)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection, Optional

from core.policy_validator import PolicyValidator
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import (
    RuntimePolicy,
    group_of,
    load_runtime_policy,
    weights_for,
)
from core.runtime_weighted_selector import (
    NoEligibleCandidateError,
    SelectionEvidence,
    SelectionKey,
    select_candidate,
    weighted_select,
)

__all__ = [
    "ALLOWED_ROLES",
    "DispatchDecision",
    "NoEligibleCandidateError",
    "PolicyEndpointUnverifiedError",
    "dispatch_role",
    "select_for_role",
]

ALLOWED_ROLES = ("SCOUT", "STANDARD_WORKER", "DEEP_WORKER")


class PolicyEndpointUnverifiedError(RuntimeError):
    """Raised when unverified endpoint filtering leaves zero eligible candidates."""
    pass


@dataclass(frozen=True)
class DispatchDecision:
    """Immutable shadow role dispatch decision and audit evidence."""
    endpoint_id: str
    model: str
    effort: str
    table_used: str
    excluded_unverified: tuple[str, ...]
    mode: RoutingMode
    role: str
    failure_domain: str
    independence_group: str
    core_validation_status: str
    selection_evidence: SelectionEvidence

    @property
    def selected_endpoint(self) -> str:
        return self.endpoint_id

    @property
    def excluded_endpoints(self) -> tuple[str, ...]:
        return self.selection_evidence.excluded_candidates

    @property
    def effective_candidates(self) -> tuple[str, ...]:
        return self.selection_evidence.effective_candidates


def _domain_of(policy: RuntimePolicy, endpoint_id: str) -> str:
    """Resolve the capacity/failure domain name for an endpoint."""
    for dom_name, domain_obj in policy.domains.items():
        if endpoint_id in domain_obj.endpoint_ids:
            return dom_name
    return "unknown"


def dispatch_role(
    policy: RuntimePolicy,
    role: str,
    key: SelectionKey,
    excluded_endpoints: Optional[Collection[str]] = None,
    validator: Optional[PolicyValidator] = None,
) -> DispatchDecision:
    """Compute shadow-mode weighted dispatch decision for SCOUT/STANDARD_WORKER/DEEP_WORKER.

    Task 5 uses the BASE table only for Standard Worker (OX overlay is Task 6).
    """
    return select_for_role(
        policy=policy,
        role=role,
        key=key,
        excluded_endpoints=excluded_endpoints,
        validator=validator,
    )


def select_for_role(
    policy: RuntimePolicy,
    role: str,
    key: SelectionKey,
    *,
    excluded_endpoints: Optional[Collection[str]] = None,
    validator: Optional[PolicyValidator] = None,
) -> DispatchDecision:
    """Select endpoint for role, mode, and key using Task 2 policy and Task 3 selector."""
    if role not in ALLOWED_ROLES:
        raise ValueError(
            f"Unsupported role {role!r} for role dispatch; expected one of {ALLOWED_ROLES}. "
            "BOSS is handled via Task 4 and VERIFIER via Task 7."
        )

    if not isinstance(key, SelectionKey):
        raise TypeError(f"key must be a SelectionKey instance, got {type(key).__name__}")

    mode = key.mode

    # Task 5 contract: STANDARD_WORKER uses base table only (ox_overlay_active=False)
    table_used = "base"
    candidates = weights_for(policy, role, mode, ox_overlay_active=False)

    # Pre-selection filtering: gather unverified endpoints in policy metadata + caller exclusions
    combined_exclusions = set(excluded_endpoints or ())
    unverified_found: list[str] = []

    for ep, meta in policy.endpoint_resolution.items():
        if not meta.get("verified", False) or meta.get("eligibility") != "eligible":
            combined_exclusions.add(ep)
            if any(c.endpoint_id == ep for c in candidates):
                unverified_found.append(ep)

    try:
        selection_ev = weighted_select(candidates, key, exclude=combined_exclusions)
    except NoEligibleCandidateError as exc:
        if unverified_found and not (set(c.endpoint_id for c in candidates) - set(unverified_found)):
            raise PolicyEndpointUnverifiedError(
                f"Filtering unverified endpoints {unverified_found} left zero eligible candidates for {role}/{mode.value}."
            ) from exc
        raise

    selected_ep = selection_ev.selected_endpoint
    meta = policy.endpoint_resolution[selected_ep]
    model = meta.get("model", "")
    effort = meta.get("effort", "")
    dom = _domain_of(policy, selected_ep)
    grp = group_of(policy, selected_ep)

    # Core PolicyValidator check
    if validator is None:
        validator = PolicyValidator()

    core_ok, core_err = validator.validate_requested_endpoint(selected_ep)
    if core_ok:
        eff_ok, eff_err = validator.validate_endpoint_effort(selected_ep, effort)
        core_status = "REQUEST_VALID" if eff_ok else f"CORE_REQUEST_INVALID: {eff_err}"
    else:
        core_status = f"CORE_REQUEST_INVALID: {core_err}"

    return DispatchDecision(
        endpoint_id=selected_ep,
        model=model,
        effort=effort,
        table_used=table_used,
        excluded_unverified=tuple(sorted(unverified_found)),
        mode=mode,
        role=role,
        failure_domain=dom,
        independence_group=grp,
        core_validation_status=core_status,
        selection_evidence=selection_ev,
    )
