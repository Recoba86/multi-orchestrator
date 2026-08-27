#!/usr/bin/env python3
"""Offline Shadow-vs-Legacy Acceptance Report (Task 11).

Composes Tasks 1-10 components in deterministic scenarios, compares against
legacy baseline bindings, classifies all differences (MATCH, EXPECTED_DIVERGENCE,
PRE_ACTIVATION_GAP, BLOCKER), and outputs an activation-readiness verdict.

Usage:
    shadow_report.py [--json]
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_boss_binding import legacy_binding, shadow_boss_binding
from core.runtime_reviewer_selector import select_reviewer
from core.runtime_role_dispatch import dispatch_role
from core.runtime_routing_mode import GROK_MODE, SOL_MODE
from core.runtime_routing_policy import group_of, load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


def generate_acceptance_report() -> dict:
    policy = load_runtime_policy(CONFIG_PATH)
    validator = PolicyValidator()

    results = {
        "MATCH": [],
        "EXPECTED_DIVERGENCE": [],
        "PRE_ACTIVATION_GAP": [],
        "BLOCKER": [],
    }

    # -------------------------------------------------------------------------
    # Scenario A: SolMode Boss (Healthy)
    # -------------------------------------------------------------------------
    sol_dec = shadow_boss_binding(mode=SOL_MODE, policy=policy, validator=validator)
    sol_leg = legacy_binding("sol-luna-orchestrator-v2")
    if sol_dec.selected_endpoint == sol_leg == "SOL_HIGH" and sol_dec.core_validation_status == "REQUEST_VALID":
        results["MATCH"].append({
            "scenario": "A_SOLMODE_BOSS_HEALTHY",
            "legacy": sol_leg,
            "shadow": sol_dec.selected_endpoint,
            "status": "REQUEST_VALID",
            "details": "SolMode selects SOL_HIGH matching legacy wrapper hard binding",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "A_SOLMODE_BOSS_HEALTHY",
            "reason": f"Expected SOL_HIGH match, got {sol_dec.selected_endpoint}",
        })

    # -------------------------------------------------------------------------
    # Scenario B: GrokMode Boss (Healthy)
    # -------------------------------------------------------------------------
    grok_dec = shadow_boss_binding(mode=GROK_MODE, policy=policy, validator=validator)
    grok_leg = legacy_binding("grok-orchestrator-v2")
    if grok_dec.selected_endpoint == grok_leg == "GROK_4_6_HIGH" and grok_dec.core_validation_status == "REQUEST_VALID":
        results["MATCH"].append({
            "scenario": "B_GROKMODE_BOSS_HEALTHY",
            "legacy": grok_leg,
            "shadow": grok_dec.selected_endpoint,
            "status": "REQUEST_VALID",
            "details": "GrokMode selects GROK_4_6_HIGH matching legacy wrapper hard binding",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "B_GROKMODE_BOSS_HEALTHY",
            "reason": f"Expected GROK_4_6_HIGH match, got {grok_dec.selected_endpoint}",
        })

    # -------------------------------------------------------------------------
    # Scenario C: SolMode Boss with gpt_plus cooldown (Health Failover)
    # -------------------------------------------------------------------------
    cooldown_dec = shadow_boss_binding(
        mode=SOL_MODE,
        policy=policy,
        domain_eligible=lambda dom: dom != "gpt_plus",
        validator=validator,
    )
    if cooldown_dec.selected_endpoint == "GROK_4_6_HIGH" and cooldown_dec.mode == SOL_MODE:
        results["EXPECTED_DIVERGENCE"].append({
            "scenario": "C_SOLMODE_GPT_PLUS_COOLDOWN",
            "legacy": "SOL_HIGH (statically bound)",
            "shadow": "GROK_4_6_HIGH (health failover)",
            "mode": "SolMode (unmodified)",
            "details": "Under gpt_plus cooldown, shadow Boss skips to GROK_4_6_HIGH while persistent mode remains SolMode",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "C_SOLMODE_GPT_PLUS_COOLDOWN",
            "reason": f"Expected GROK_4_6_HIGH in SolMode, got {cooldown_dec.selected_endpoint} in {cooldown_dec.mode}",
        })

    # -------------------------------------------------------------------------
    # Scenario D: Scout Roles (SolMode and GrokMode)
    # -------------------------------------------------------------------------
    k_scout_sol = SelectionKey(mission_id="scout-test", role="SCOUT", ordinal=0, mode=SOL_MODE)
    dec_scout_sol = dispatch_role(policy, "SCOUT", k_scout_sol, validator=validator)

    k_scout_grok = SelectionKey(mission_id="scout-test", role="SCOUT", ordinal=0, mode=GROK_MODE)
    dec_scout_grok = dispatch_role(policy, "SCOUT", k_scout_grok, validator=validator)

    gpt_plus_eps = set(policy.domains["gpt_plus"].endpoint_ids)
    if dec_scout_grok.selected_endpoint not in gpt_plus_eps and dec_scout_sol.core_validation_status == "REQUEST_VALID":
        results["EXPECTED_DIVERGENCE"].append({
            "scenario": "D_SCOUT_WEIGHTED_POLICY",
            "legacy": "Static chain GEMINI_FLASH_HIGH -> DEEPSEEK_FLASH -> PLUS_LUNA",
            "shadow": f"SolMode: {dec_scout_sol.selected_endpoint} (70/20/10), GrokMode: {dec_scout_grok.selected_endpoint} (87.5/12.5)",
            "details": "Scout dispatches according to mode-aware weighted policy with zero GPT Plus in GrokMode",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "D_SCOUT_WEIGHTED_POLICY",
            "reason": "Scout failed GrokMode zero-GPT guard or Core validation",
        })

    # -------------------------------------------------------------------------
    # Scenario E & F: Standard Worker Base & OX Overlay
    # -------------------------------------------------------------------------
    k_worker_base = SelectionKey(mission_id="worker-base", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
    dec_worker_base = dispatch_role(policy, "STANDARD_WORKER", k_worker_base, validator=validator)

    # Under production config (OX disabled), Worker dispatches against base table
    if dec_worker_base.table_used == "base":
        results["EXPECTED_DIVERGENCE"].append({
            "scenario": "E_STANDARD_WORKER_BASE_POLICY",
            "legacy": "Static chain GEMINI -> PLUS_LUNA -> DEEPSEEK",
            "shadow": f"Base: {dec_worker_base.selected_endpoint} (50/35/15 in SolMode, 75/25 in GrokMode)",
            "details": "Worker dispatches against mode-aware base table (OX disabled in production)",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "E_STANDARD_WORKER_BASE_POLICY",
            "reason": "Worker base table selection failed",
        })


    # -------------------------------------------------------------------------
    # Scenario G: Deep Worker (SolMode Luna xhigh filtered)
    # -------------------------------------------------------------------------
    k_deep = SelectionKey(mission_id="deep-test", role="DEEP_WORKER", ordinal=0, mode=SOL_MODE)
    dec_deep = dispatch_role(policy, "DEEP_WORKER", k_deep, validator=validator)
    if "PLUS_LUNA_XHIGH" in dec_deep.excluded_unverified and dec_deep.selected_endpoint != "PLUS_LUNA_XHIGH":
        results["EXPECTED_DIVERGENCE"].append({
            "scenario": "G_DEEP_WORKER_LUNA_XHIGH_FILTERED",
            "legacy": "Static chain DEEPSEEK_PRO -> PLUS_LUNA -> GEMINI",
            "shadow": f"Selected: {dec_deep.selected_endpoint} (renormalized 60/25/5 without PLUS_LUNA_XHIGH)",
            "details": "PLUS_LUNA_XHIGH filtered pre-selection due to unverified status; survivors renormalize",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "G_DEEP_WORKER_LUNA_XHIGH_FILTERED",
            "reason": "Deep Worker failed to pre-filter unverified PLUS_LUNA_XHIGH",
        })

    # -------------------------------------------------------------------------
    # Scenario H & I: Reviewer Independence (Sol & Luna implementers)
    # -------------------------------------------------------------------------
    k_rev_sol = SelectionKey(mission_id="rev-sol", role="VERIFIER", ordinal=0, mode=SOL_MODE)
    dec_rev_sol = select_reviewer(policy, "SOL_HIGH", k_rev_sol, validator=validator)

    k_rev_luna = SelectionKey(mission_id="rev-luna", role="VERIFIER", ordinal=0, mode=SOL_MODE)
    dec_rev_luna = select_reviewer(policy, "PLUS_LUNA", k_rev_luna, validator=validator)

    sol_cands_groups = [group_of(policy, ep) for ep in dec_rev_sol.effective_candidates]
    luna_cands_groups = [group_of(policy, ep) for ep in dec_rev_luna.effective_candidates]

    if "gpt_family" not in sol_cands_groups and "gpt_family" not in luna_cands_groups:
        results["EXPECTED_DIVERGENCE"].append({
            "scenario": "H_REVIEWER_INDEPENDENCE_BIDIRECTIONAL",
            "legacy": "Static verifier list with potential self/family conflicts",
            "shadow": f"Sol implementer reviewers: {dec_rev_sol.effective_candidates}, Luna reviewers: {dec_rev_luna.effective_candidates}",
            "details": "Bidirectional gpt_family exclusion strictly enforced (Sol cannot review Luna, Luna cannot review Sol)",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "H_REVIEWER_INDEPENDENCE_BIDIRECTIONAL",
            "reason": "Reviewer independence violation: gpt_family candidate present for gpt_family implementer",
        })

    # STEP_3_7_FLASH runtime validity in Task 12
    k_gap_step = SelectionKey(mission_id="gap-step", role="SCOUT", ordinal=0, mode=SOL_MODE)
    dec_gap_step = dispatch_role(
        policy, "SCOUT", k_gap_step,
        excluded_endpoints={"GEMINI_FLASH_HIGH", "PLUS_LUNA"},
        validator=validator,
    )
    if dec_gap_step.endpoint_id == "STEP_3_7_FLASH" and dec_gap_step.core_validation_status == "REQUEST_VALID":
        results["EXPECTED_DIVERGENCE"].append({
            "scenario": "STEP_3_7_FLASH_RUNTIME_ACTIVATED",
            "legacy": "Unregistered endpoint in legacy Core",
            "shadow": "STEP_3_7_FLASH (REQUEST_VALID under runtime catalog)",
            "details": "STEP_3_7_FLASH activated as valid runtime endpoint in Task 12",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "STEP_3_7_FLASH_RUNTIME_ACTIVATED",
            "reason": f"STEP_3_7_FLASH was expected to be REQUEST_VALID, got {dec_gap_step.core_validation_status}",
        })
    # Status of OX_ALPHA: Intentionally disabled and unselectable per Task 12 Operator Activation Amendment
    ox_meta = policy.endpoint_resolution.get("OX_ALPHA", {})
    if not ox_meta.get("enabled", True) and not ox_meta.get("verified", True):
        results["EXPECTED_DIVERGENCE"].append({
            "scenario": "OX_ALPHA_INTENTIONALLY_DISABLED",
            "legacy": "Planned OX-ALpha overlay",
            "shadow": "OX_ALPHA disabled in production config (zero dispatches)",
            "details": "OX-ALpha is commercially unavailable for this deployment; disabled and not activated",
        })
    else:
        results["BLOCKER"].append({
            "scenario": "OX_ALPHA_DISABLED_CHECK",
            "reason": "OX_ALPHA was expected to be disabled in production config",
        })

    # Overall verdict: READY if zero blockers
    is_ready = len(results["BLOCKER"]) == 0
    verdict = "READY_FOR_TASK_12" if is_ready else "BLOCKED_FOR_TASK_12"
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "counts": {
            "MATCH": len(results["MATCH"]),
            "EXPECTED_DIVERGENCE": len(results["EXPECTED_DIVERGENCE"]),
            "PRE_ACTIVATION_GAP": len(results["PRE_ACTIVATION_GAP"]),
            "BLOCKER": len(results["BLOCKER"]),
        },
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shadow-vs-Legacy Acceptance Report Generator.")
    parser.add_argument("--json", action="store_true", help="Output report as structured JSON.")
    args = parser.parse_args(argv)

    report = generate_acceptance_report()

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("=== Shadow vs Legacy Acceptance Report ===")
    print(f"Timestamp: {report['timestamp_utc']}")
    print(f"STATUS: {report['verdict']}\n")

    print(f"MATCH: {report['counts']['MATCH']}")
    for r in report["results"]["MATCH"]:
        print(f"  [MATCH] {r['scenario']}: {r['shadow']} == {r['legacy']} ({r['details']})")

    print(f"\nEXPECTED_DIVERGENCE: {report['counts']['EXPECTED_DIVERGENCE']}")
    for r in report["results"]["EXPECTED_DIVERGENCE"]:
        print(f"  [DIVERGENCE] {r['scenario']}: {r['shadow']} vs Legacy: {r['legacy']}")

    print(f"\nPRE_ACTIVATION_GAP: {report['counts']['PRE_ACTIVATION_GAP']}")
    for r in report["results"]["PRE_ACTIVATION_GAP"]:
        print(f"  [GAP] {r['item']} ({r['endpoint']}): {r['status']} -> Owned by {r['owned_by']}")

    print(f"\nBLOCKER: {report['counts']['BLOCKER']}")
    for r in report["results"]["BLOCKER"]:
        print(f"  [BLOCKER] {r['scenario']}: {r['reason']}")

    print("\n" + "=" * 45)
    if report["verdict"] == "READY_FOR_TASK_12":
        print("Verdict: READY_FOR_TASK_12 (Operator review and explicit sign-off required before Task 12)")
    else:
        print("Verdict: BLOCKED_FOR_TASK_12")

    return 0


if __name__ == "__main__":
    sys.exit(main())
