"""Reviewer Independence Selector (Tasks 7 & 12).

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§5.8, §13.2)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Tasks 7 & 12)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Collection, Optional

from core.policy_validator import PolicyValidator
from core.runtime_endpoint_validator import RuntimeEndpointValidator
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import (
    CandidateWeight,
    RuntimePolicy,
    group_of,
    load_runtime_policy,
)
from core.runtime_weighted_selector import (
    NoEligibleCandidateError,
    SelectionEvidence,
    SelectionKey,
    weighted_select,
)

__all__ = [
    "NoEligibleReviewerError",
    "ReviewerDecision",
    "select_reviewer",
]


class NoEligibleReviewerError(RuntimeError):
    """Raised when reviewer filtering leaves zero eligible candidates."""
    pass


@dataclass(frozen=True)
class ReviewerDecision:
    """Immutable audit evidence for independent reviewer selection."""
    mode: RoutingMode
    implementer_endpoint: str
    implementer_independence_group: str
    configured_reviewer_candidates: tuple[str, ...]
    same_group_excluded: tuple[str, ...]
    mode_excluded: tuple[str, ...]
    statically_ineligible: tuple[str, ...]
    caller_excluded: tuple[str, ...]
    effective_candidates: tuple[str, ...]
    selected_endpoint: str
    selected_model: str
    selected_effort: str
    selected_failure_domain: str
    selected_independence_group: str
    selection_evidence: SelectionEvidence
    core_validation_status: str
    decision_reason: str
    stage_order: tuple[str, ...] = (
        "1_implementer_validation",
        "2_same_independence_group_exclusion",
        "3_mode_eligibility_exclusion",
        "4_static_policy_eligibility",
        "5_caller_and_health_exclusions",
        "6_task3_weighted_selection",
        "7_core_policy_validation",
    )

    @property
    def endpoint_id(self) -> str:
        return self.selected_endpoint


def _domain_of(policy: RuntimePolicy, endpoint_id: str) -> str:
    """Resolve the capacity/failure domain name for an endpoint."""
    for dom_name, domain_obj in policy.domains.items():
        if endpoint_id in domain_obj.endpoint_ids:
            return dom_name
    return "unknown"


def select_reviewer(
    policy: RuntimePolicy,
    implementer_endpoint: str,
    key: SelectionKey,
    excluded_endpoints: Optional[Collection[str]] = None,
    validator: Optional[PolicyValidator] = None,
    domain_eligible: Optional[Callable[[str], bool]] = None,
) -> ReviewerDecision:
    """Select an independent reviewer using the normative 5-stage filter and Task-3 selector."""
    if not isinstance(key, SelectionKey):
        raise TypeError(f"key must be a SelectionKey instance, got {type(key).__name__}")

    mode = key.mode

    # Stage 1: Validate implementer endpoint and derive its independence group
    if implementer_endpoint not in policy.endpoint_resolution:
        raise ValueError(f"Unknown implementer endpoint {implementer_endpoint!r}")

    imp_group = group_of(policy, implementer_endpoint)

    # Obtain configured reviewer candidate weights for implementer group + mode
    rev_key = (imp_group, mode)
    if rev_key not in policy.reviewer_tables:
        raise ValueError(f"No reviewer table configured for implementer group {imp_group!r} and mode {mode.value!r}")

    configured_cands = policy.reviewer_tables[rev_key]
    configured_ep_ids = tuple(c.endpoint_id for c in configured_cands)

    # Stage 2: Exclude candidates in implementer's same independence group
    same_group_excluded: list[str] = []
    stage2_survivors: list[CandidateWeight] = []
    for c in configured_cands:
        c_grp = group_of(policy, c.endpoint_id)
        if c_grp == imp_group:
            same_group_excluded.append(c.endpoint_id)
        else:
            stage2_survivors.append(c)

    # Stage 3: Mode eligibility (GrokMode forbids gpt_plus failure domain)
    mode_excluded: list[str] = []
    stage3_survivors: list[CandidateWeight] = []
    gpt_plus_eps = set(policy.domains.get("gpt_plus", None).endpoint_ids if "gpt_plus" in policy.domains else ())

    for c in stage2_survivors:
        if mode == GROK_MODE and c.endpoint_id in gpt_plus_eps:
            mode_excluded.append(c.endpoint_id)
        else:
            stage3_survivors.append(c)

    # Stage 4: Static endpoint eligibility (enabled == True, verified == True, eligibility == 'eligible')
    static_ineligible: list[str] = []
    stage4_survivors: list[CandidateWeight] = []
    for c in stage3_survivors:
        meta = policy.endpoint_resolution.get(c.endpoint_id, {})
        if not meta.get("enabled", True) or not meta.get("verified", False) or meta.get("eligibility") != "eligible":
            static_ineligible.append(c.endpoint_id)
        else:
            stage4_survivors.append(c)

    # Stage 5: Caller-provided exclusions and dynamic domain health filtering
    caller_excluded: list[str] = []
    caller_excl_set = set(excluded_endpoints or ())
    stage5_survivors: list[CandidateWeight] = []

    for c in stage4_survivors:
        ep = c.endpoint_id
        dom = _domain_of(policy, ep)
        if ep in caller_excl_set:
            caller_excluded.append(ep)
        elif domain_eligible is not None and not domain_eligible(dom):
            caller_excluded.append(ep)
        else:
            stage5_survivors.append(c)

    if not stage5_survivors:
        raise NoEligibleReviewerError(
            f"No eligible reviewer candidate remaining for implementer {implementer_endpoint} "
            f"({imp_group}) in {mode.value} after filtering."
        )

    # Stage 6: Exactly one Task-3 weighted selection over survivors
    try:
        selection_ev = weighted_select(stage5_survivors, key)
    except NoEligibleCandidateError as exc:
        raise NoEligibleReviewerError("Reviewer selection failed closed with zero candidates.") from exc

    selected_ep = selection_ev.selected_endpoint
    selected_meta = policy.endpoint_resolution[selected_ep]
    model = selected_meta.get("model", "")
    effort = selected_meta.get("effort", "")
    dom = _domain_of(policy, selected_ep)
    grp = group_of(policy, selected_ep)

    # Stage 7: Runtime Endpoint validation (Core OR runtime catalog)
    endpoint_val = RuntimeEndpointValidator(core_validator=validator, runtime_policy=policy)
    val_ok, val_err = endpoint_val.validate_endpoint(selected_ep, effort=effort)
    core_status = "REQUEST_VALID" if val_ok else f"CORE_REQUEST_INVALID: {val_err}"

    return ReviewerDecision(
        mode=mode,
        implementer_endpoint=implementer_endpoint,
        implementer_independence_group=imp_group,
        configured_reviewer_candidates=configured_ep_ids,
        same_group_excluded=tuple(sorted(same_group_excluded)),
        mode_excluded=tuple(sorted(mode_excluded)),
        statically_ineligible=tuple(sorted(static_ineligible)),
        caller_excluded=tuple(sorted(caller_excluded)),
        effective_candidates=tuple(c.endpoint_id for c in stage5_survivors),
        selected_endpoint=selected_ep,
        selected_model=model,
        selected_effort=effort,
        selected_failure_domain=dom,
        selected_independence_group=grp,
        selection_evidence=selection_ev,
        core_validation_status=core_status,
        decision_reason=f"Selected independent reviewer for {implementer_endpoint} ({imp_group}) in {mode.value}",
    )
