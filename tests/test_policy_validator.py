#!/usr/bin/env python3
"""
Production Dynamic Policy Validator Tests for Multi Orchestrator RC3.
Validates production policy_validator.py against authoritative Core.
"""

import unittest
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "core"))

from policy_validator import PolicyValidator

class TestProductionPolicyValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = PolicyValidator()

    def test_boss_binding_resolution(self):
        ok, err, binding = self.validator.validate_boss_binding("sol-luna-orchestrator-v2")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(binding["required_boss_endpoint"], "SOL_HIGH")

        ok, err, binding = self.validator.validate_boss_binding("unregistered-skill")
        self.assertFalse(ok)
        self.assertIn("BOSS_BINDING_UNAVAILABLE", err)

    def test_controller_cannot_self_promote(self):
        ok, err = self.validator.validate_role_not_controller_self_promotion("ROOT_CONTROLLER", "BOSS")
        self.assertFalse(ok)
        self.assertEqual(err, "REJECT_CONTROLLER_SELF_PROMOTION")

        ok, err = self.validator.validate_role_not_controller_self_promotion("ROOT_CONTROLLER", "ROOT_CONTROLLER")
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_endpoint_validation(self):
        ok, err = self.validator.validate_requested_endpoint("GEMINI_FLASH_HIGH")
        self.assertTrue(ok)
        self.assertIsNone(err)

        ok, err = self.validator.validate_requested_endpoint("NON_EXISTENT_MODEL")
        self.assertFalse(ok)
        self.assertIn("REJECT_UNKNOWN_ENDPOINT", err)

    def test_effort_validation_and_policy_caps(self):
        ok, err = self.validator.validate_endpoint_effort("PLUS_LUNA", "max")
        self.assertTrue(ok)
        self.assertIsNone(err)

        ok, err = self.validator.validate_endpoint_effort("OCG_LUNA", "high")
        self.assertTrue(ok)
        self.assertIsNone(err)

        # OCG_LUNA has policy_max_effort: high
        ok, err = self.validator.validate_endpoint_effort("OCG_LUNA", "max")
        self.assertFalse(ok)
        self.assertIn("REJECT_EFFORT_EXCEEDS_POLICY", err)

        # DEEPSEEK_PRO does not accept low
        ok, err = self.validator.validate_endpoint_effort("DEEPSEEK_PRO", "low")
        self.assertFalse(ok)
        self.assertIn("REJECT_UNACCEPTED_EFFORT", err)

    def test_controller_execution_binding_positive(self):
        # A. Valid Gemini binding
        ok, err = self.validator.validate_controller_execution_binding(
            "GEMINI_FLASH_HIGH",
            "nine-router/ag/gemini-3.7-flash-high",
            "high",
            "GEMINI_FLASH_HIGH",
            "nine-router/ag/gemini-3.7-flash-high",
            "high"
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_same_endpoint_wrong_requested_model_fails(self):
        # B. Same endpoint ID, wrong requested model
        ok, err = self.validator.validate_controller_execution_binding(
            "GEMINI_FLASH_HIGH",
            "gpt-5.6-luna",
            "high",
            "GEMINI_FLASH_HIGH",
            "nine-router/ag/gemini-3.7-flash-high",
            "high"
        )
        self.assertFalse(ok)
        self.assertIn("REJECT_REQUESTED_MODEL_MISMATCH", err)

    def test_same_endpoint_wrong_actual_model_fails(self):
        # C. Same endpoint ID, correct requested model, WRONG actual model (Controller model substitution)
        ok, err = self.validator.validate_controller_execution_binding(
            "GEMINI_FLASH_HIGH",
            "nine-router/ag/gemini-3.7-flash-high",
            "high",
            "GEMINI_FLASH_HIGH",
            "gpt-5.6-luna",
            "high"
        )
        self.assertFalse(ok)
        self.assertIn("REJECT_CONTROLLER_MODEL_SUBSTITUTION", err)

    def test_endpoint_and_effort_substitution_fails(self):
        # D. Endpoint substitution
        ok, err = self.validator.validate_controller_execution_binding(
            "GEMINI_FLASH_HIGH",
            "nine-router/ag/gemini-3.7-flash-high",
            "high",
            "PLUS_LUNA",
            "gpt-5.6-luna",
            "high"
        )
        self.assertFalse(ok)
        self.assertIn("REJECT_CONTROLLER_SUBSTITUTION", err)

        # E. Effort substitution
        ok, err = self.validator.validate_controller_execution_binding(
            "PLUS_LUNA",
            "gpt-5.6-luna",
            "max",
            "PLUS_LUNA",
            "gpt-5.6-luna",
            "low"
        )
        self.assertFalse(ok)
        self.assertIn("REJECT_CONTROLLER_SUBSTITUTION", err)

    def test_verifier_independence_and_luna_family_conflict(self):
        ok, err = self.validator.validate_verifier_independence("GEMINI_FLASH_HIGH", "PLUS_LUNA")
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Self verification conflict
        ok, err = self.validator.validate_verifier_independence("GEMINI_FLASH_HIGH", "GEMINI_FLASH_HIGH")
        self.assertFalse(ok)
        self.assertEqual(err, "REJECT_SELF_VERIFICATION")

        # Luna model-family conflict: PLUS_LUNA and OCG_LUNA
        ok, err = self.validator.validate_verifier_independence("PLUS_LUNA", "OCG_LUNA")
        self.assertFalse(ok)
        self.assertIn("REJECT_MODEL_FAMILY_CONFLICT", err)

        ok, err = self.validator.validate_verifier_independence("OCG_LUNA", "PLUS_LUNA")
        self.assertFalse(ok)
        self.assertIn("REJECT_MODEL_FAMILY_CONFLICT", err)

    def test_single_authority_dynamic_core_fixture(self):
        # Proves changing Core fixture alters validator behavior without modifying validator source
        custom_core = """```yaml
endpoints:
  - id: CUSTOM_TEST_ENDPOINT
    family: custom
    model: custom/model-1
    accepted_efforts: [low]
```"""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(custom_core)
            temp_path = f.name
        try:
            custom_validator = PolicyValidator(core_path=temp_path)
            ok, _ = custom_validator.validate_requested_endpoint("CUSTOM_TEST_ENDPOINT")
            self.assertTrue(ok)
            ok, _ = custom_validator.validate_requested_endpoint("GEMINI_FLASH_HIGH")
            self.assertFalse(ok) # Not in custom fixture
        finally:
            os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
