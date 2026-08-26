"""Runtime routing declarative policy schema and validation (Task 2).

Normative reference:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Mapping
import yaml

from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode

__all__ = [
    "CandidateWeight",
    "FailureDomain",
    "RuntimePolicy",
    "PolicyValidationError",
    "load_runtime_policy",
    "group_of",
    "weights_for",
    "boss_chain_for",
]


class PolicyValidationError(ValueError):
    """Raised when runtime routing policy configuration fails static schema validation."""
    pass


@dataclass(frozen=True)
class CandidateWeight:
    endpoint_id: str
    weight: float


@dataclass(frozen=True)
class FailureDomain:
    name: str
    endpoint_ids: tuple[str, ...]


@dataclass(frozen=True)
class RuntimePolicy:
    domains: dict[str, FailureDomain]
    independence_groups: dict[str, tuple[str, ...]]
    boss_chains: dict[RoutingMode, tuple[str, ...]]
    role_weights: dict[tuple[str, RoutingMode, bool], tuple[CandidateWeight, ...]]
    reviewer_tables: dict[tuple[str, RoutingMode], tuple[CandidateWeight, ...]]
    global_targets: dict[str, float]
    ox_overlay: str
    endpoint_resolution: dict[str, dict[str, Any]]


_KNOWN_TOP_LEVEL_KEYS = {
    "schema_version",
    "failure_domains",
    "independence_groups",
    "global_targets",
    "ox_overlay",
    "endpoint_resolution",
    "boss_chains",
    "role_weights",
    "reviewer_tables",
}

_ALLOWED_OX_STATES = {"enabled", "disabled", "auto"}


def _fail(reason: str) -> None:
    raise PolicyValidationError(f"INVALID_RUNTIME_POLICY: {reason}")


def _validate_weight_number(val: Any, ctx: str) -> float:
    if isinstance(val, bool):
        _fail(f"boolean value {val} passed as weight/target in {ctx}")
    if not isinstance(val, (int, float)):
        _fail(f"non-numeric value {val!r} in {ctx}")
    if math.isnan(val) or math.isinf(val):
        _fail(f"NaN or infinite weight in {ctx}")
    if val < 0:
        _fail(f"negative weight {val} in {ctx}")
    return float(val)


def group_of(policy: RuntimePolicy, endpoint_id: str) -> str:
    """Resolve an endpoint id to its unique independence group."""
    for grp, endpoints in policy.independence_groups.items():
        if endpoint_id in endpoints:
            return grp
    _fail(f"endpoint {endpoint_id!r} is not mapped in any independence group")
    raise AssertionError("unreachable")


def weights_for(
    policy: RuntimePolicy,
    role: str,
    mode: RoutingMode,
    ox_overlay_active: bool = False,
) -> tuple[CandidateWeight, ...]:
    """Obtain the candidate weight table for role, mode, and overlay status."""
    key = (role, mode, ox_overlay_active)
    if key in policy.role_weights:
        return policy.role_weights[key]
    # Fallback to base if overlay inactive or overlay not defined
    fallback_key = (role, mode, False)
    if fallback_key in policy.role_weights:
        return policy.role_weights[fallback_key]
    _fail(f"no weight table for role={role!r}, mode={mode.value!r}, overlay={ox_overlay_active}")
    raise AssertionError("unreachable")


def boss_chain_for(policy: RuntimePolicy, mode: RoutingMode) -> tuple[str, ...]:
    """Obtain the ordered Boss priority chain for the given mode."""
    if mode in policy.boss_chains:
        return policy.boss_chains[mode]
    _fail(f"no boss chain defined for mode {mode.value!r}")
    raise AssertionError("unreachable")


def load_runtime_policy(path: Path) -> RuntimePolicy:
    """Load and statically validate runtime-routing policy from YAML."""
    if not path.exists():
        _fail(f"policy file does not exist at {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except Exception as exc:
        _fail(f"corrupt YAML syntax: {exc}")

    if not isinstance(raw, dict):
        _fail(f"root schema must be a mapping, got {type(raw).__name__}")

    extra_keys = set(raw.keys()) - _KNOWN_TOP_LEVEL_KEYS
    if extra_keys:
        _fail(f"unknown top-level key(s): {', '.join(sorted(extra_keys))}")

    missing_keys = _KNOWN_TOP_LEVEL_KEYS - set(raw.keys())
    if missing_keys:
        _fail(f"missing required top-level key(s): {', '.join(sorted(missing_keys))}")

    # Schema version
    version = raw["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        _fail(f"unsupported schema_version: {version!r}")

    # Endpoint resolution
    raw_endpoints = raw["endpoint_resolution"]
    if not isinstance(raw_endpoints, dict) or not raw_endpoints:
        _fail("endpoint_resolution must be a non-empty mapping")

    parsed_endpoints: dict[str, dict[str, Any]] = {}
    for ep_id, ep_data in raw_endpoints.items():
        if not isinstance(ep_id, str) or not ep_id:
            _fail("endpoint identifier must be a non-empty string")
        if not isinstance(ep_data, dict):
            _fail(f"endpoint {ep_id} data must be a mapping")
        model = ep_data.get("model")
        if not isinstance(model, str) or not model:
            _fail(f"endpoint {ep_id} missing valid model string")
        if model.startswith("nine-router/cx/"):
            _fail(f"prohibited nine-router/cx model {model} in endpoint {ep_id}")
        verified = ep_data.get("verified", False)
        if isinstance(verified, bool) and not verified:
            eligibility = ep_data.get("eligibility")
            if eligibility != "unverified":
                _fail(f"unverified endpoint {ep_id} must have eligibility='unverified'")
        if ep_id == "PLUS_LUNA_XHIGH" and verified is True:
            _fail("PLUS_LUNA_XHIGH must remain unverified until upstream gate passes")
        parsed_endpoints[ep_id] = ep_data

    # Failure domains
    raw_domains = raw["failure_domains"]
    if not isinstance(raw_domains, dict) or not raw_domains:
        _fail("failure_domains must be a non-empty mapping")
    parsed_domains: dict[str, FailureDomain] = {}
    for dom_name, ep_list in raw_domains.items():
        if not isinstance(dom_name, str) or not dom_name:
            _fail("failure domain name must be a non-empty string")
        if not isinstance(ep_list, list) or not ep_list:
            _fail(f"failure domain {dom_name} must contain a non-empty endpoint list")
        for ep in ep_list:
            if ep not in parsed_endpoints:
                _fail(f"failure domain {dom_name} references unknown endpoint {ep}")
        parsed_domains[dom_name] = FailureDomain(name=dom_name, endpoint_ids=tuple(ep_list))

    # Independence groups
    raw_groups = raw["independence_groups"]
    if not isinstance(raw_groups, dict) or not raw_groups:
        _fail("independence_groups must be a non-empty mapping")
    parsed_groups: dict[str, tuple[str, ...]] = {}
    all_grouped_endpoints = set()
    for grp_name, ep_list in raw_groups.items():
        if not isinstance(grp_name, str) or not grp_name:
            _fail("independence group name must be a non-empty string")
        if not isinstance(ep_list, list) or not ep_list:
            _fail(f"independence group {grp_name} must contain a non-empty endpoint list")
        for ep in ep_list:
            if ep not in parsed_endpoints:
                _fail(f"independence group {grp_name} references unknown endpoint {ep}")
            if ep in all_grouped_endpoints:
                _fail(f"endpoint {ep} appears in multiple independence groups")
            all_grouped_endpoints.add(ep)
        parsed_groups[grp_name] = tuple(ep_list)

    ungrouped = set(parsed_endpoints.keys()) - all_grouped_endpoints
    if ungrouped:
        _fail(f"endpoints missing from independence_groups: {', '.join(sorted(ungrouped))}")

    # Global targets
    raw_targets = raw["global_targets"]
    if not isinstance(raw_targets, dict):
        _fail("global_targets must be a mapping")
    parsed_targets: dict[str, float] = {}
    target_sum = 0.0
    for pool, target_val in raw_targets.items():
        if pool not in parsed_domains:
            _fail(f"global_targets references unknown pool/domain {pool}")
        w = _validate_weight_number(target_val, f"global_targets[{pool}]")
        parsed_targets[pool] = w
        target_sum += w
    if not math.isclose(target_sum, 100.0, abs_tol=1e-9):
        _fail(f"global_targets sum ({target_sum}) != 100.0")

    # OX Overlay
    ox_state = raw["ox_overlay"]
    if ox_state not in _ALLOWED_OX_STATES:
        _fail(f"invalid ox_overlay state {ox_state!r}; must be one of {sorted(_ALLOWED_OX_STATES)}")

    # Boss chains
    raw_boss = raw["boss_chains"]
    if not isinstance(raw_boss, dict):
        _fail("boss_chains must be a mapping")
    parsed_boss: dict[RoutingMode, tuple[str, ...]] = {}
    for mode_key, chain in raw_boss.items():
        if mode_key == "SolMode":
            mode_enum = SOL_MODE
        elif mode_key == "GrokMode":
            mode_enum = GROK_MODE
        else:
            _fail(f"unknown mode name in boss_chains: {mode_key!r}")
        if not isinstance(chain, list) or not chain:
            _fail(f"boss chain for {mode_key} must be a non-empty list")
        for ep in chain:
            if ep not in parsed_endpoints:
                _fail(f"boss chain for {mode_key} references unknown endpoint {ep}")
            if mode_enum == GROK_MODE:
                if ep in parsed_domains.get("gpt_plus", FailureDomain("", ())).endpoint_ids:
                    _fail(f"GrokMode boss chain includes prohibited gpt_plus endpoint {ep}")
        parsed_boss[mode_enum] = tuple(chain)

    # Role weights
    raw_roles = raw["role_weights"]
    if not isinstance(raw_roles, dict):
        _fail("role_weights must be a mapping")
    parsed_role_weights: dict[tuple[str, RoutingMode, bool], tuple[CandidateWeight, ...]] = {}

    gpt_plus_endpoints = set(parsed_domains.get("gpt_plus", FailureDomain("", ())).endpoint_ids)

    for role_name, modes_data in raw_roles.items():
        if not isinstance(modes_data, dict):
            _fail(f"role {role_name} data must be a mapping")
        for mode_key, table_types in modes_data.items():
            if mode_key == "SolMode":
                mode_enum = SOL_MODE
            elif mode_key == "GrokMode":
                mode_enum = GROK_MODE
            else:
                _fail(f"unknown mode {mode_key!r} in role_weights[{role_name}]")
            if not isinstance(table_types, dict):
                _fail(f"role_weights[{role_name}][{mode_key}] must be a mapping of base/overlay")

            for is_overlay, tbl_key in [(False, "base"), (True, "overlay")]:
                if tbl_key not in table_types:
                    continue
                candidates_list = table_types[tbl_key]
                if not isinstance(candidates_list, list) or not candidates_list:
                    _fail(f"role {role_name}/{mode_key}/{tbl_key} table must be a non-empty list")
                cands: list[CandidateWeight] = []
                cand_endpoints = set()
                total_w = 0.0
                for c_entry in candidates_list:
                    if not isinstance(c_entry, dict):
                        _fail(f"candidate entry in {role_name}/{mode_key}/{tbl_key} must be a mapping")
                    ep = c_entry.get("endpoint")
                    if ep not in parsed_endpoints:
                        _fail(f"unknown endpoint {ep} in {role_name}/{mode_key}/{tbl_key}")
                    if ep in cand_endpoints:
                        _fail(f"duplicate endpoint {ep} in {role_name}/{mode_key}/{tbl_key}")
                    cand_endpoints.add(ep)

                    w = _validate_weight_number(
                        c_entry.get("weight"), f"{role_name}/{mode_key}/{tbl_key}/{ep}"
                    )
                    total_w += w

                    # Static role prohibitions
                    if role_name == "SCOUT":
                        if ep == "SOL_HIGH" or ep in parsed_groups.get("supergrok", ()) or ep in parsed_groups.get("opus", ()):
                            _fail(f"SCOUT table includes prohibited endpoint {ep}")
                    if role_name in ("STANDARD_WORKER", "DEEP_WORKER"):
                        if ep == "SOL_HIGH":
                            _fail(f"{role_name} includes prohibited endpoint SOL_HIGH")
                    if mode_enum == GROK_MODE:
                        if ep in gpt_plus_endpoints:
                            _fail(f"GrokMode {role_name} table includes prohibited gpt_plus endpoint {ep}")

                    cands.append(CandidateWeight(endpoint_id=ep, weight=w))

                if not math.isclose(total_w, 100.0, abs_tol=1e-9):
                    _fail(f"{role_name}/{mode_key}/{tbl_key} table weight sum ({total_w}) != 100.0")

                parsed_role_weights[(role_name, mode_enum, is_overlay)] = tuple(cands)

    # Reviewer tables
    raw_reviewer = raw["reviewer_tables"]
    if not isinstance(raw_reviewer, dict):
        _fail("reviewer_tables must be a mapping")
    parsed_reviewer: dict[tuple[str, RoutingMode], tuple[CandidateWeight, ...]] = {}

    for grp_key, modes_dict in raw_reviewer.items():
        if grp_key not in parsed_groups:
            _fail(f"reviewer_tables keyed by unknown independence group {grp_key}")
        if not isinstance(modes_dict, dict):
            _fail(f"reviewer_tables[{grp_key}] must be a mapping of modes")
        for mode_key, c_list in modes_dict.items():
            if mode_key == "SolMode":
                mode_enum = SOL_MODE
            elif mode_key == "GrokMode":
                mode_enum = GROK_MODE
            else:
                _fail(f"unknown mode {mode_key!r} in reviewer_tables[{grp_key}]")
            if not isinstance(c_list, list) or not c_list:
                _fail(f"reviewer table for {grp_key}/{mode_key} must be a non-empty list")
            cands = []
            cand_eps = set()
            rev_total = 0.0
            for c_entry in c_list:
                if not isinstance(c_entry, dict):
                    _fail(f"candidate entry in reviewer table {grp_key}/{mode_key} must be a mapping")
                ep = c_entry.get("endpoint")
                if ep not in parsed_endpoints:
                    _fail(f"unknown endpoint {ep} in reviewer table {grp_key}/{mode_key}")
                if ep in cand_eps:
                    _fail(f"duplicate endpoint {ep} in reviewer table {grp_key}/{mode_key}")
                cand_eps.add(ep)
                w = _validate_weight_number(
                    c_entry.get("weight"), f"reviewer_tables[{grp_key}][{mode_key}][{ep}]"
                )
                rev_total += w

                # GPT independence rule: GPT implementer cannot be reviewed by GPT candidate
                if grp_key == "gpt_family" and ep in parsed_groups.get("gpt_family", ()):
                    _fail(f"GPT-family implementer cannot be reviewed by GPT-family candidate {ep}")

                if mode_enum == GROK_MODE and ep in gpt_plus_endpoints:
                    _fail(f"GrokMode reviewer table includes prohibited gpt_plus endpoint {ep}")

                cands.append(CandidateWeight(endpoint_id=ep, weight=w))

            if not math.isclose(rev_total, 100.0, abs_tol=1e-9):
                _fail(f"reviewer table {grp_key}/{mode_key} weight sum ({rev_total}) != 100.0")

            parsed_reviewer[(grp_key, mode_enum)] = tuple(cands)

    return RuntimePolicy(
        domains=parsed_domains,
        independence_groups=parsed_groups,
        boss_chains=parsed_boss,
        role_weights=parsed_role_weights,
        reviewer_tables=parsed_reviewer,
        global_targets=parsed_targets,
        ox_overlay=ox_state,
        endpoint_resolution=parsed_endpoints,
    )
