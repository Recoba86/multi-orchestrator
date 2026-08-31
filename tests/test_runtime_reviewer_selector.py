"""Reviewer independence selector: primary-first after family exclusion."""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_reviewer_selector import NoEligibleReviewerError, select_reviewer
from core.runtime_routing_mode import GROK_MODE, SOL_MODE
from core.runtime_routing_policy import group_of, load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class ReviewerIndependenceSelectorTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    def _key(self, ordinal=0, mode=SOL_MODE):
        return SelectionKey(mission_id="rev", role="VERIFIER", ordinal=ordinal, mode=mode)

    def test_implementer_group_derivation(self):
        self.assertEqual(group_of(self.policy, "SOL_HIGH"), "sol_family")
        self.assertEqual(group_of(self.policy, "PLUS_LUNA"), "luna_family")
        self.assertEqual(group_of(self.policy, "PLUS_TERRA"), "terra_family")
        self.assertEqual(group_of(self.policy, "GROK_4_6_HIGH"), "supergrok")
        self.assertEqual(group_of(self.policy, "GEMINI_FLASH_HIGH"), "gemini")
        self.assertEqual(group_of(self.policy, "GEMINI_FLASH_MEDIUM"), "gemini")
        self.assertEqual(group_of(self.policy, "STEP_3_7_FLASH"), "cheap")
        self.assertEqual(group_of(self.policy, "OX_ALPHA"), "ox_combo")

    def test_unknown_implementer_fails_closed(self):
        with self.assertRaises(ValueError):
            select_reviewer(self.policy, "UNKNOWN_IMPLEMENTER", self._key(), validator=self.validator)

    def test_gemini_implementer_selects_sol_primary(self):
        d0 = select_reviewer(self.policy, "GEMINI_FLASH_HIGH", self._key(0), validator=self.validator)
        d1 = select_reviewer(self.policy, "GEMINI_FLASH_HIGH", self._key(1), validator=self.validator)
        self.assertEqual(d0.selected_endpoint, "SOL_HIGH")
        self.assertEqual(d0.selected_model, "gpt-5.6-sol")
        self.assertEqual(d1.selected_endpoint, "SOL_HIGH")
        self.assertEqual(d0.implementer_independence_group, "gemini")

    def test_sol_implementer_skips_sol_then_grok(self):
        dec = select_reviewer(self.policy, "SOL_HIGH", self._key(), validator=self.validator)
        self.assertEqual(dec.implementer_independence_group, "sol_family")
        self.assertEqual(dec.selected_endpoint, "GROK_4_6_HIGH")
        self.assertNotIn("SOL_HIGH", dec.effective_candidates)
    def test_luna_implementer_may_be_reviewed_by_sol(self):
        dec = select_reviewer(self.policy, "PLUS_LUNA", self._key(), validator=self.validator)
        self.assertEqual(dec.implementer_independence_group, "luna_family")
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")

    def test_sol_implementer_grok_excluded_selects_opus(self):
        dec = select_reviewer(
            self.policy, "SOL_HIGH", self._key(),
            excluded_endpoints={"GROK_4_6_HIGH"}, validator=self.validator,
        )
        self.assertEqual(dec.selected_endpoint, "OPUS_COMBO")

    def test_grok_implementer_selects_sol(self):
        dec = select_reviewer(self.policy, "GROK_4_6_HIGH", self._key(), validator=self.validator)
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")

    def test_grok_implementer_grokmode_skips_sol(self):
        dec = select_reviewer(self.policy, "GROK_4_6_HIGH", self._key(mode=GROK_MODE), validator=self.validator)
        self.assertEqual(dec.selected_endpoint, "OPUS_COMBO")
        self.assertNotEqual(dec.selected_endpoint, "SOL_HIGH")

    def test_domain_eligible_health_filtering(self):
        def domain_eligible(dom):
            return dom != "gpt_plus"
        dec = select_reviewer(
            self.policy, "GEMINI_FLASH_HIGH", self._key(),
            validator=self.validator, domain_eligible=domain_eligible,
        )
        self.assertEqual(dec.selected_endpoint, "GROK_4_6_HIGH")

    def test_explicit_exclusions_and_exhaustion(self):
        dec = select_reviewer(
            self.policy, "SOL_HIGH", self._key(),
            excluded_endpoints={"GROK_4_6_HIGH"}, validator=self.validator,
        )
        self.assertEqual(dec.selected_endpoint, "OPUS_COMBO")
        with self.assertRaises(NoEligibleReviewerError):
            select_reviewer(
                self.policy, "SOL_HIGH", self._key(),
                excluded_endpoints={"GROK_4_6_HIGH", "OPUS_COMBO", "GEMINI_FLASH_HIGH"},
                validator=self.validator,
            )


if __name__ == "__main__":
    unittest.main()
