"""Tests for Task 7: Reviewer Independence Selector.

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§5.8)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 7)
"""

import collections
from pathlib import Path
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_reviewer_selector import (
    NoEligibleReviewerError,
    ReviewerDecision,
    select_reviewer,
)
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import RuntimePolicy, group_of, load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class ReviewerIndependenceSelectorTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    # -------------------------------------------------------------------------
    # 1. IDENTITY / GROUP DERIVATION
    # -------------------------------------------------------------------------
    def test_implementer_group_derivation(self):
        self.assertEqual(group_of(self.policy, "SOL_HIGH"), "gpt_family")
        self.assertEqual(group_of(self.policy, "PLUS_LUNA"), "gpt_family")
        self.assertEqual(group_of(self.policy, "PLUS_LUNA_XHIGH"), "gpt_family")
        self.assertEqual(group_of(self.policy, "OCG_LUNA"), "gpt_family")
        self.assertEqual(group_of(self.policy, "GROK_4_6_HIGH"), "supergrok")
        self.assertEqual(group_of(self.policy, "GEMINI_FLASH_HIGH"), "gemini")
        self.assertEqual(group_of(self.policy, "STEP_3_7_FLASH"), "cheap")
        self.assertEqual(group_of(self.policy, "OX_ALPHA"), "ox_combo")

    def test_unknown_implementer_fails_closed(self):
        key = SelectionKey(mission_id="m1", role="VERIFIER", ordinal=0, mode=SOL_MODE)
        with self.assertRaises(ValueError):
            select_reviewer(self.policy, "UNKNOWN_IMPLEMENTER", key, validator=self.validator)

    # -------------------------------------------------------------------------
    # 2. GPT FAMILY IMPLEMENTER (SOL / LUNA / OCG_LUNA)
    # -------------------------------------------------------------------------
    def test_sol_implementer_excludes_all_gpt_family(self):
        key = SelectionKey(mission_id="m-sol-imp", role="VERIFIER", ordinal=0, mode=SOL_MODE)
        dec = select_reviewer(self.policy, "SOL_HIGH", key, validator=self.validator)
        self.assertEqual(dec.implementer_independence_group, "gpt_family")
        self.assertNotIn("SOL_HIGH", dec.effective_candidates)
        self.assertNotIn("PLUS_LUNA", dec.effective_candidates)
        self.assertNotIn("PLUS_LUNA_XHIGH", dec.effective_candidates)
        self.assertNotIn("OCG_LUNA", dec.effective_candidates)
        # Assert effective candidates contain zero gpt_family endpoints
        for ep in dec.effective_candidates:
            self.assertNotEqual(group_of(self.policy, ep), "gpt_family")

    def test_luna_implementer_excludes_all_gpt_family_bidirectional(self):
        key = SelectionKey(mission_id="m-luna-imp", role="VERIFIER", ordinal=0, mode=SOL_MODE)
        dec = select_reviewer(self.policy, "PLUS_LUNA", key, validator=self.validator)
        self.assertEqual(dec.implementer_independence_group, "gpt_family")
        self.assertNotIn("SOL_HIGH", dec.effective_candidates)
        self.assertNotIn("PLUS_LUNA", dec.effective_candidates)
        self.assertEqual(set(dec.effective_candidates), {"GROK_4_6_HIGH", "GEMINI_FLASH_HIGH", "OPUS_4_6_THINKING"})

    def test_gpt_family_implementer_distribution_65_25_10(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="gpt-dist", role="VERIFIER", ordinal=i, mode=SOL_MODE)
            dec = select_reviewer(self.policy, "SOL_HIGH", key, validator=self.validator)
            counts[dec.endpoint_id] += 1
            self.assertNotEqual(dec.selected_independence_group, "gpt_family")

        self.assertAlmostEqual(counts["GROK_4_6_HIGH"] / n, 0.65, delta=0.02)
        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.25, delta=0.02)
        self.assertAlmostEqual(counts["OPUS_4_6_THINKING"] / n, 0.10, delta=0.02)
        self.assertEqual(counts["PLUS_LUNA"], 0)
        self.assertEqual(counts["SOL_HIGH"], 0)

    # -------------------------------------------------------------------------
    # 3. GROK IMPLEMENTER
    # -------------------------------------------------------------------------
    def test_grok_implementer_solmode_distribution_60_20_20(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="grok-dist-sol", role="VERIFIER", ordinal=i, mode=SOL_MODE)
            dec = select_reviewer(self.policy, "GROK_4_6_HIGH", key, validator=self.validator)
            counts[dec.endpoint_id] += 1
            self.assertNotEqual(dec.endpoint_id, "GROK_4_6_HIGH")

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.60, delta=0.02)
        self.assertAlmostEqual(counts["OPUS_4_6_THINKING"] / n, 0.20, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.20, delta=0.02)
        self.assertEqual(counts["GROK_4_6_HIGH"], 0)

    def test_grok_implementer_grokmode_distribution_75_25(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="grok-dist-grok", role="VERIFIER", ordinal=i, mode=GROK_MODE)
            dec = select_reviewer(self.policy, "GROK_4_6_HIGH", key, validator=self.validator)
            counts[dec.endpoint_id] += 1
            self.assertNotEqual(dec.endpoint_id, "GROK_4_6_HIGH")
            self.assertNotEqual(dec.selected_independence_group, "gpt_family")

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.75, delta=0.02)
        self.assertAlmostEqual(counts["OPUS_4_6_THINKING"] / n, 0.25, delta=0.02)
        self.assertEqual(counts["PLUS_LUNA"], 0)
        self.assertEqual(counts["GROK_4_6_HIGH"], 0)

    # -------------------------------------------------------------------------
    # 4. GEMINI IMPLEMENTER
    # -------------------------------------------------------------------------
    def test_gemini_implementer_solmode_distribution_60_25_15(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="gemini-dist-sol", role="VERIFIER", ordinal=i, mode=SOL_MODE)
            dec = select_reviewer(self.policy, "GEMINI_FLASH_HIGH", key, validator=self.validator)
            counts[dec.endpoint_id] += 1
            self.assertNotEqual(dec.endpoint_id, "GEMINI_FLASH_HIGH")

        self.assertAlmostEqual(counts["GROK_4_6_HIGH"] / n, 0.60, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.25, delta=0.02)
        self.assertAlmostEqual(counts["OPUS_4_6_THINKING"] / n, 0.15, delta=0.02)
        self.assertEqual(counts["GEMINI_FLASH_HIGH"], 0)

    def test_gemini_implementer_grokmode_distribution_75_25(self):
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="gemini-dist-grok", role="VERIFIER", ordinal=i, mode=GROK_MODE)
            dec = select_reviewer(self.policy, "GEMINI_FLASH_HIGH", key, validator=self.validator)
            counts[dec.endpoint_id] += 1
            self.assertNotEqual(dec.endpoint_id, "GEMINI_FLASH_HIGH")
            self.assertNotEqual(dec.selected_independence_group, "gpt_family")

        self.assertAlmostEqual(counts["GROK_4_6_HIGH"] / n, 0.75, delta=0.02)
        self.assertAlmostEqual(counts["OPUS_4_6_THINKING"] / n, 0.25, delta=0.02)
        self.assertEqual(counts["PLUS_LUNA"], 0)

    # -------------------------------------------------------------------------
    # 5. STEP / OX IMPLEMENTER
    # -------------------------------------------------------------------------
    def test_step_and_ox_implementer_distribution_60_30_10(self):
        for imp in ("STEP_3_7_FLASH", "OX_ALPHA"):
            counts = collections.Counter()
            n = 5000
            for i in range(n):
                key = SelectionKey(mission_id=f"step-ox-{imp}", role="VERIFIER", ordinal=i, mode=SOL_MODE)
                dec = select_reviewer(self.policy, imp, key, validator=self.validator)
                counts[dec.endpoint_id] += 1
                self.assertNotEqual(dec.endpoint_id, imp)

            self.assertAlmostEqual(counts["GROK_4_6_HIGH"] / n, 0.60, delta=0.02)
            self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.30, delta=0.02)
            self.assertAlmostEqual(counts["OPUS_4_6_THINKING"] / n, 0.10, delta=0.02)
            self.assertEqual(counts["OX_ALPHA"], 0)
            self.assertEqual(counts["STEP_3_7_FLASH"], 0)

    # -------------------------------------------------------------------------
    # 6. EXCLUSIONS & FAIL-CLOSED EXHAUSTION
    # -------------------------------------------------------------------------
    def test_explicit_exclusions_and_exhaustion(self):
        key = SelectionKey(mission_id="excl-rev", role="VERIFIER", ordinal=0, mode=SOL_MODE)
        # Exclude Grok and Gemini when implementer is Sol -> only Opus remains
        dec = select_reviewer(
            self.policy,
            "SOL_HIGH",
            key,
            excluded_endpoints={"GROK_4_6_HIGH", "GEMINI_FLASH_HIGH"},
            validator=self.validator,
        )
        self.assertEqual(dec.endpoint_id, "OPUS_4_6_THINKING")
        self.assertEqual(dec.effective_candidates, ("OPUS_4_6_THINKING",))
        self.assertIn("GROK_4_6_HIGH", dec.caller_excluded)

        # Exclude all survivors -> fail closed
        with self.assertRaises(NoEligibleReviewerError):
            select_reviewer(
                self.policy,
                "SOL_HIGH",
                key,
                excluded_endpoints={"GROK_4_6_HIGH", "GEMINI_FLASH_HIGH", "OPUS_4_6_THINKING"},
                validator=self.validator,
            )

    def test_domain_eligible_health_filtering(self):
        key = SelectionKey(mission_id="health-rev", role="VERIFIER", ordinal=0, mode=SOL_MODE)
        # Mark supergrok and gemini unhealthy -> Opus selected
        dec = select_reviewer(
            self.policy,
            "SOL_HIGH",
            key,
            domain_eligible=lambda dom: dom not in ("supergrok", "gemini"),
            validator=self.validator,
        )
        self.assertEqual(dec.endpoint_id, "OPUS_4_6_THINKING")

    # -------------------------------------------------------------------------
    # 7. DETERMINISM & CORE VALIDATOR INTEGRATION
    # -------------------------------------------------------------------------
    def test_deterministic_and_core_valid(self):
        key = SelectionKey(mission_id="det-rev", role="VERIFIER", ordinal=42, mode=SOL_MODE)
        d1 = select_reviewer(self.policy, "SOL_HIGH", key, validator=self.validator)
        d2 = select_reviewer(self.policy, "SOL_HIGH", key, validator=self.validator)
        self.assertEqual(d1, d2)
        self.assertEqual(d1.core_validation_status, "REQUEST_VALID")
        self.assertIsInstance(d1, ReviewerDecision)


if __name__ == "__main__":
    unittest.main()
