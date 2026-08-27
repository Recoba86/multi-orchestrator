"""Tests for shadow Scout, Standard Worker, and Deep Worker dispatch (Task 5).

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§5.1, §5.2, §5.3, §5.5a, §5.6, §5.7, §13.1)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 5)
"""

import collections
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_role_dispatch import (
    ALLOWED_ROLES,
    DispatchDecision,
    NoEligibleCandidateError,
    PolicyEndpointUnverifiedError,
    dispatch_role,
)
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import RuntimePolicy, load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class RuntimeRoleDispatchTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    # -------------------------------------------------------------------------
    # SCOUT
    # -------------------------------------------------------------------------
    def test_scout_solmode_deterministic(self):
        key = SelectionKey(mission_id="scout-test", role="SCOUT", ordinal=0, mode=SOL_MODE)
        d1 = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
        d2 = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
        self.assertEqual(d1, d2)
        self.assertIsInstance(d1, DispatchDecision)
        self.assertEqual(d1.role, "SCOUT")
        self.assertEqual(d1.mode, SOL_MODE)
        self.assertEqual(d1.table_used, "base")

    def test_scout_grokmode_deterministic(self):
        key = SelectionKey(mission_id="scout-test", role="SCOUT", ordinal=0, mode=GROK_MODE)
        d1 = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
        d2 = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
        self.assertEqual(d1, d2)
        self.assertEqual(d1.mode, GROK_MODE)

    def test_scout_solmode_distribution_70_20_10(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="scout-dist", role="SCOUT", ordinal=i, mode=SOL_MODE)
            dec = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
            counts[dec.endpoint_id] += 1

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.70, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.20, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.10, delta=0.02)

    def test_scout_grokmode_distribution_87_5_12_5(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="scout-dist-grok", role="SCOUT", ordinal=i, mode=GROK_MODE)
            dec = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
            counts[dec.endpoint_id] += 1

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.875, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.125, delta=0.02)

    def test_scout_never_yields_forbidden_models(self):
        forbidden = {"SOL_HIGH", "GROK_4_6_HIGH", "OPUS_4_6_THINKING"}
        for mode in (SOL_MODE, GROK_MODE):
            for i in range(500):
                key = SelectionKey(mission_id="scout-forbid", role="SCOUT", ordinal=i, mode=mode)
                dec = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
                self.assertNotIn(dec.endpoint_id, forbidden)

    # -------------------------------------------------------------------------
    # STANDARD_WORKER (Base only)
    # -------------------------------------------------------------------------
    def test_standard_worker_solmode_distribution_50_35_15(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="worker-dist-sol", role="STANDARD_WORKER", ordinal=i, mode=SOL_MODE)
            dec = dispatch_role(self.policy, "STANDARD_WORKER", key, validator=self.validator)
            counts[dec.endpoint_id] += 1

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.50, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.35, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.15, delta=0.02)

    def test_standard_worker_grokmode_distribution_75_25(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="worker-dist-grok", role="STANDARD_WORKER", ordinal=i, mode=GROK_MODE)
            dec = dispatch_role(self.policy, "STANDARD_WORKER", key, validator=self.validator)
            counts[dec.endpoint_id] += 1

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.75, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.25, delta=0.02)

    def test_standard_worker_never_uses_ox_or_sol(self):
        for mode in (SOL_MODE, GROK_MODE):
            for i in range(500):
                key = SelectionKey(mission_id="worker-base-guard", role="STANDARD_WORKER", ordinal=i, mode=mode)
                dec = dispatch_role(self.policy, "STANDARD_WORKER", key, validator=self.validator)
                self.assertNotEqual(dec.endpoint_id, "OX_ALPHA")
                self.assertNotEqual(dec.endpoint_id, "SOL_HIGH")
                self.assertEqual(dec.table_used, "base")

    # -------------------------------------------------------------------------
    # DEEP_WORKER (Unverified Luna xhigh pre-filtered)
    # -------------------------------------------------------------------------
    def test_deep_worker_solmode_renormalized_distribution_60_25_5(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="deep-dist-sol", role="DEEP_WORKER", ordinal=i, mode=SOL_MODE)
            dec = dispatch_role(self.policy, "DEEP_WORKER", key, validator=self.validator)
            counts[dec.endpoint_id] += 1
            self.assertIn("PLUS_LUNA_XHIGH", dec.excluded_unverified)

        self.assertEqual(counts["PLUS_LUNA_XHIGH"], 0)
        self.assertEqual(counts["PLUS_LUNA"], 0)  # No silent substitution!
        # Ratios over 90:
        self.assertAlmostEqual(counts["GROK_4_6_HIGH"] / n, 60.0 / 90.0, delta=0.02)
        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 25.0 / 90.0, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 5.0 / 90.0, delta=0.02)

    def test_deep_worker_grokmode_distribution_67_28_5(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="deep-dist-grok", role="DEEP_WORKER", ordinal=i, mode=GROK_MODE)
            dec = dispatch_role(self.policy, "DEEP_WORKER", key, validator=self.validator)
            counts[dec.endpoint_id] += 1

        self.assertAlmostEqual(counts["GROK_4_6_HIGH"] / n, 0.67, delta=0.02)
        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.28, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.05, delta=0.02)

    # -------------------------------------------------------------------------
    # GENERIC & ROLE BOUNDARIES
    # -------------------------------------------------------------------------
    def test_unsupported_roles_rejected(self):
        key = SelectionKey(mission_id="role-test", role="SCOUT", ordinal=0, mode=SOL_MODE)
        for bad_role in ("BOSS", "VERIFIER", "PREMIUM_SECOND_OPINION", "planner", "worker", "reviewer", "UNKNOWN"):
            with self.assertRaises(ValueError, msg=f"Should reject role {bad_role}"):
                dispatch_role(self.policy, bad_role, key, validator=self.validator)

    def test_explicit_exclusions_honored(self):
        key = SelectionKey(mission_id="excl-test", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(
            self.policy,
            "STANDARD_WORKER",
            key,
            excluded_endpoints={"GEMINI_FLASH_HIGH", "PLUS_LUNA"},
            validator=self.validator,
        )
        self.assertEqual(dec.endpoint_id, "STEP_3_7_FLASH")
        self.assertIn("GEMINI_FLASH_HIGH", dec.excluded_endpoints)
        self.assertIn("PLUS_LUNA", dec.excluded_endpoints)

    def test_all_candidates_excluded_fails_closed(self):
        key = SelectionKey(mission_id="fail-test", role="SCOUT", ordinal=0, mode=GROK_MODE)
        with self.assertRaises(NoEligibleCandidateError):
            dispatch_role(
                self.policy,
                "SCOUT",
                key,
                excluded_endpoints={"GEMINI_FLASH_HIGH", "STEP_3_7_FLASH"},
                validator=self.validator,
            )

    # -------------------------------------------------------------------------
    # CORE VALIDATION EVIDENCE & NO REROLL
    # -------------------------------------------------------------------------
    def test_core_valid_and_core_invalid_evidence(self):
        # GEMINI_FLASH_HIGH is in Core registry -> REQUEST_VALID
        key_valid = SelectionKey(mission_id="core-val", role="SCOUT", ordinal=0, mode=SOL_MODE)
        # Force a selection of GEMINI_FLASH_HIGH by excluding others
        dec_valid = dispatch_role(
            self.policy,
            "SCOUT",
            key_valid,
            excluded_endpoints={"PLUS_LUNA", "STEP_3_7_FLASH"},
            validator=self.validator,
        )
        self.assertEqual(dec_valid.endpoint_id, "GEMINI_FLASH_HIGH")
        self.assertEqual(dec_valid.core_validation_status, "REQUEST_VALID")

        # In Task 12, STEP_3_7_FLASH is validated and active -> REQUEST_VALID
        key_step = SelectionKey(mission_id="core-step", role="SCOUT", ordinal=0, mode=SOL_MODE)
        dec_step = dispatch_role(
            self.policy,
            "SCOUT",
            key_step,
            excluded_endpoints={"GEMINI_FLASH_HIGH", "PLUS_LUNA"},
            validator=self.validator,
        )
        self.assertEqual(dec_step.endpoint_id, "STEP_3_7_FLASH")
        self.assertEqual(dec_step.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # METADATA & POLICY UNMUTATED
    # -------------------------------------------------------------------------
    def test_metadata_fields_populated_and_policy_unmutated(self):
        orig_weights = dict(self.policy.role_weights)
        key = SelectionKey(mission_id="meta-test", role="SCOUT", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
        self.assertEqual(self.policy.role_weights, orig_weights)
        self.assertIn(dec.failure_domain, self.policy.domains)
        self.assertIn(dec.independence_group, self.policy.independence_groups)
        self.assertEqual(dec.model, self.policy.endpoint_resolution[dec.endpoint_id]["model"])
        self.assertEqual(dec.effort, self.policy.endpoint_resolution[dec.endpoint_id]["effort"])


if __name__ == "__main__":
    unittest.main()
