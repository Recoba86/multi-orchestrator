"""Primary-first Scout/Standard Worker/Deep Worker dispatch tests."""

from pathlib import Path
import unittest
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_role_dispatch import (
    DispatchDecision,
    NoEligibleCandidateError,
    dispatch_role,
)
from core.runtime_routing_mode import GROK_MODE, SOL_MODE
from core.runtime_routing_policy import load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class RuntimeRoleDispatchTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    def _key(self, role, ordinal=0, mode=SOL_MODE, mission="m"):
        return SelectionKey(mission_id=mission, role=role, ordinal=ordinal, mode=mode)

    def test_scout_solmode_replicates_primary_across_ordinals(self):
        d0 = dispatch_role(self.policy, "SCOUT", self._key("SCOUT", 0), validator=self.validator)
        d1 = dispatch_role(self.policy, "SCOUT", self._key("SCOUT", 1), validator=self.validator)
        self.assertEqual(d0.endpoint_id, "GEMINI_FLASH_MEDIUM")
        self.assertEqual(d0.model, "nine-router/ag/gemini-3.7-flash-medium")
        self.assertEqual(d1.endpoint_id, "GEMINI_FLASH_MEDIUM")
        self.assertEqual(d0.table_used, "base")

    def test_scout_failover_only_when_primary_excluded(self):
        dec = dispatch_role(
            self.policy, "SCOUT", self._key("SCOUT"),
            excluded_endpoints={"GEMINI_FLASH_MEDIUM"}, validator=self.validator,
        )
        self.assertEqual(dec.endpoint_id, "QWEN_3_8_FLASH")

    def test_scout_never_yields_forbidden_models(self):
        forbidden = {"SOL_HIGH", "GROK_4_6_HIGH", "OPUS_COMBO", "PLUS_LUNA"}
        for mode in (SOL_MODE, GROK_MODE):
            for i in range(20):
                dec = dispatch_role(self.policy, "SCOUT", self._key("SCOUT", i, mode), validator=self.validator)
                self.assertNotIn(dec.endpoint_id, forbidden)

    def test_standard_worker_replicates_gemini_high(self):
        d0 = dispatch_role(self.policy, "STANDARD_WORKER", self._key("STANDARD_WORKER", 0), validator=self.validator)
        d1 = dispatch_role(self.policy, "STANDARD_WORKER", self._key("STANDARD_WORKER", 1), validator=self.validator)
        self.assertEqual(d0.endpoint_id, "GEMINI_FLASH_HIGH")
        self.assertEqual(d1.endpoint_id, "GEMINI_FLASH_HIGH")
        self.assertNotEqual(d0.endpoint_id, "SOL_HIGH")

    def test_standard_worker_failover_luna(self):
        dec = dispatch_role(
            self.policy, "STANDARD_WORKER", self._key("STANDARD_WORKER"),
            excluded_endpoints={"GEMINI_FLASH_HIGH"}, validator=self.validator,
        )
        self.assertEqual(dec.endpoint_id, "PLUS_LUNA")

    def test_deep_worker_replicates_grok(self):
        d0 = dispatch_role(self.policy, "DEEP_WORKER", self._key("DEEP_WORKER", 0), validator=self.validator)
        d1 = dispatch_role(self.policy, "DEEP_WORKER", self._key("DEEP_WORKER", 1), validator=self.validator)
        self.assertEqual(d0.endpoint_id, "GROK_4_6_HIGH")
        self.assertEqual(d1.endpoint_id, "GROK_4_6_HIGH")
        self.assertNotEqual(d0.endpoint_id, "SOL_HIGH")

    def test_unsupported_roles_rejected(self):
        key = self._key("SCOUT")
        for bad_role in ("BOSS", "VERIFIER", "PREMIUM_SECOND_OPINION", "planner"):
            with self.assertRaises(ValueError):
                dispatch_role(self.policy, bad_role, key, validator=self.validator)

    def test_all_candidates_excluded_fails_closed(self):
        with self.assertRaises(NoEligibleCandidateError):
            dispatch_role(
                self.policy, "SCOUT", self._key("SCOUT", mode=GROK_MODE),
                excluded_endpoints={"GEMINI_FLASH_MEDIUM", "QWEN_3_8_FLASH"},
                validator=self.validator,
            )

    def test_core_valid_and_core_invalid_evidence(self):
        dec_valid = dispatch_role(self.policy, "SCOUT", self._key("SCOUT"), validator=self.validator)
        self.assertEqual(dec_valid.endpoint_id, "GEMINI_FLASH_MEDIUM")
        self.assertTrue(str(dec_valid.core_validation_status).startswith("REQUEST_VALID") or dec_valid.core_validation_status == "REQUEST_VALID")
        self.assertIsInstance(dec_valid, DispatchDecision)

    def test_scout_solmode_deterministic(self):
        key = self._key("SCOUT")
        self.assertEqual(
            dispatch_role(self.policy, "SCOUT", key, validator=self.validator),
            dispatch_role(self.policy, "SCOUT", key, validator=self.validator),
        )

    def test_scout_grokmode_deterministic(self):
        key = self._key("SCOUT", mode=GROK_MODE)
        d1 = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
        d2 = dispatch_role(self.policy, "SCOUT", key, validator=self.validator)
        self.assertEqual(d1, d2)
        self.assertEqual(d1.endpoint_id, "GEMINI_FLASH_MEDIUM")


if __name__ == "__main__":
    unittest.main()
