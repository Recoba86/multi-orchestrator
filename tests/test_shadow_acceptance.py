"""Tests for Task 11: Shadow-vs-Legacy Acceptance Gate.

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§12)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 11)
"""

from pathlib import Path
import subprocess
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_boss_binding import legacy_binding, shadow_boss_binding
from core.runtime_reviewer_selector import select_reviewer
from core.runtime_role_dispatch import dispatch_role
from core.runtime_routing_health import FailureKind, domain_eligible, record_failure
from core.runtime_routing_mode import GROK_MODE, SOL_MODE
from core.runtime_routing_policy import RuntimePolicy, group_of, load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

REPORT_SCRIPT = REPO_ROOT / "scripts" / "shadow_report.py"
CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class ShadowAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    # -------------------------------------------------------------------------
    # 1. NOMINAL BOSS ACCEPTANCE: MATCH
    # -------------------------------------------------------------------------
    def test_solmode_boss_healthy_matches_legacy(self):
        dec = shadow_boss_binding(mode=SOL_MODE, policy=self.policy, validator=self.validator)
        leg = legacy_binding("sol-luna-orchestrator-v2")
        self.assertEqual(dec.selected_endpoint, leg)
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    def test_grokmode_boss_healthy_matches_legacy(self):
        dec = shadow_boss_binding(mode=GROK_MODE, policy=self.policy, validator=self.validator)
        leg = legacy_binding("grok-orchestrator-v2")
        self.assertEqual(dec.selected_endpoint, leg)
        self.assertEqual(dec.selected_endpoint, "GROK_4_6_HIGH")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # 2. HEALTH COOLDOWN FAILOVER: EXPECTED_DIVERGENCE (NO MODE MUTATION)
    # -------------------------------------------------------------------------
    def test_solmode_boss_under_gpt_cooldown_expected_divergence(self):
        # When gpt_plus is unhealthy, shadow Boss falls over to GROK_4_6_HIGH while mode remains SolMode
        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            domain_eligible=lambda dom: dom != "gpt_plus",
            validator=self.validator,
        )
        self.assertEqual(dec.selected_endpoint, "GROK_4_6_HIGH")
        self.assertEqual(dec.mode, SOL_MODE)
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # 3. GROKMODE ZERO GPT-PLUS DEFENSE
    # -------------------------------------------------------------------------
    def test_grokmode_zero_gpt_plus_across_all_roles(self):
        gpt_plus_eps = set(self.policy.domains["gpt_plus"].endpoint_ids)
        # Boss
        dec_boss = shadow_boss_binding(mode=GROK_MODE, policy=self.policy, validator=self.validator)
        self.assertNotIn(dec_boss.selected_endpoint, gpt_plus_eps)

        # Scout, Worker, Deep Worker
        for role in ("SCOUT", "STANDARD_WORKER", "DEEP_WORKER"):
            for ord_i in range(20):
                key = SelectionKey(mission_id="grok-clean", role=role, ordinal=ord_i, mode=GROK_MODE)
                dec = dispatch_role(self.policy, role, key, validator=self.validator)
                self.assertNotIn(dec.selected_endpoint, gpt_plus_eps)

    # -------------------------------------------------------------------------
    # 4. REVIEWER INDEPENDENCE: BIDIRECTIONAL GPT_FAMILY EXCLUSION
    # -------------------------------------------------------------------------
    def test_reviewer_independence_bidirectional(self):
        # Sol implementer -> no Luna
        k_sol = SelectionKey(mission_id="rev-sol", role="VERIFIER", ordinal=0, mode=SOL_MODE)
        dec_sol = select_reviewer(self.policy, "SOL_HIGH", k_sol, validator=self.validator)
        self.assertEqual(dec_sol.implementer_independence_group, "gpt_family")
        for ep in dec_sol.effective_candidates:
            self.assertNotEqual(group_of(self.policy, ep), "gpt_family")

        # Luna implementer -> no Sol
        k_luna = SelectionKey(mission_id="rev-luna", role="VERIFIER", ordinal=0, mode=SOL_MODE)
        dec_luna = select_reviewer(self.policy, "PLUS_LUNA", k_luna, validator=self.validator)
        self.assertEqual(dec_luna.implementer_independence_group, "gpt_family")
        for ep in dec_luna.effective_candidates:
            self.assertNotEqual(group_of(self.policy, ep), "gpt_family")

    # -------------------------------------------------------------------------
    # 5. PRE-ACTIVATION GAPS: STEP_3_7_FLASH & OX_ALPHA (SURFACED, NO REROLL)
    # -------------------------------------------------------------------------
    def test_pre_activation_gaps_surfaced_truthfully_no_reroll(self):
        # STEP_3_7_FLASH is not in current Core -> CORE_REQUEST_INVALID
        key_step = SelectionKey(mission_id="gap-step", role="SCOUT", ordinal=0, mode=SOL_MODE)
        dec_step = dispatch_role(
            self.policy,
            "SCOUT",
            key_step,
            excluded_endpoints={"GEMINI_FLASH_HIGH", "PLUS_LUNA"},
            validator=self.validator,
        )
        self.assertEqual(dec_step.endpoint_id, "STEP_3_7_FLASH")
        self.assertTrue(dec_step.core_validation_status.startswith("CORE_REQUEST_INVALID"))

        # OX_ALPHA is not in current Core -> CORE_REQUEST_INVALID
        key_ox = SelectionKey(mission_id="gap-ox", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec_ox = dispatch_role(
            self.policy,
            "STANDARD_WORKER",
            key_ox,
            excluded_endpoints={"GEMINI_FLASH_HIGH", "PLUS_LUNA", "STEP_3_7_FLASH"},
            ox_runtime_eligible=True,
            validator=self.validator,
        )
        self.assertEqual(dec_ox.endpoint_id, "OX_ALPHA")
        self.assertTrue(dec_ox.core_validation_status.startswith("CORE_REQUEST_INVALID"))

    # -------------------------------------------------------------------------
    # 6. LUNA XHIGH UNVERIFIED GATE
    # -------------------------------------------------------------------------
    def test_luna_xhigh_unverified_fail_closed(self):
        key = SelectionKey(mission_id="luna-xhigh-gate", role="DEEP_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(self.policy, "DEEP_WORKER", key, validator=self.validator)
        self.assertIn("PLUS_LUNA_XHIGH", dec.excluded_unverified)
        self.assertNotEqual(dec.selected_endpoint, "PLUS_LUNA_XHIGH")

    # -------------------------------------------------------------------------
    # 7. SHADOW REPORT CLI EXECUTION & VERDICTS
    # -------------------------------------------------------------------------
    def test_shadow_report_script_execution_and_verdicts(self):
        self.assertTrue(REPORT_SCRIPT.is_file(), f"Missing {REPORT_SCRIPT}")
        res = subprocess.run(
            [sys.executable, str(REPORT_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        self.assertEqual(res.returncode, 0, f"shadow_report.py failed: {res.stderr}")
        stdout = res.stdout
        self.assertIn("=== Shadow vs Legacy Acceptance Report ===", stdout)
        self.assertIn("STATUS: READY_FOR_TASK_12", stdout)
        self.assertIn("BLOCKER: 0", stdout)
        self.assertIn("PRE_ACTIVATION_GAP:", stdout)


if __name__ == "__main__":
    unittest.main()
