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


    def test_boss_binding_required_fields_and_validation(self):
        # Test missing model, missing effort, wrong model, illegal effort, and policy cap via temp Core fixtures
        core_yaml = """```yaml
endpoints:
  - id: SOL_HIGH
    family: gpt
    model: gpt-5.6-sol
    accepted_efforts: [high]
  - id: SOL_CAPPED
    family: gpt
    model: gpt-5.6-sol
    accepted_efforts: [low, medium, high]
    policy_max_effort: medium
skill_boss_bindings:
  valid-skill:
    required_boss_endpoint: SOL_HIGH
    model: gpt-5.6-sol
    effort: high
  missing-endpoint-skill:
    model: gpt-5.6-sol
    effort: high
  missing-model-skill:
    required_boss_endpoint: SOL_HIGH
    effort: high
  missing-effort-skill:
    required_boss_endpoint: SOL_HIGH
    model: gpt-5.6-sol
  wrong-model-skill:
    required_boss_endpoint: SOL_HIGH
    model: gpt-5.6-luna
    effort: high
  illegal-effort-skill:
    required_boss_endpoint: SOL_HIGH
    model: gpt-5.6-sol
    effort: low
  capped-effort-skill:
    required_boss_endpoint: SOL_CAPPED
    model: gpt-5.6-sol
    effort: high
```"""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(core_yaml)
            temp_path = f.name
        try:
            fixture_validator = PolicyValidator(core_path=temp_path)
            
            # 1. Valid binding -> PASS
            ok, err, binding = fixture_validator.validate_boss_binding("valid-skill")
            self.assertTrue(ok)
            self.assertIsNone(err)
            self.assertEqual(binding["required_boss_endpoint"], "SOL_HIGH")

            # 2. Missing endpoint -> BLOCK (BOSS_BINDING_UNAVAILABLE)
            ok, err, _ = fixture_validator.validate_boss_binding("missing-endpoint-skill")
            self.assertFalse(ok)
            self.assertIn("BOSS_BINDING_UNAVAILABLE", err)
            self.assertIn("Missing required_boss_endpoint", err)

            # 3. Missing model -> BLOCK (BOSS_BINDING_UNAVAILABLE)
            ok, err, _ = fixture_validator.validate_boss_binding("missing-model-skill")
            self.assertFalse(ok)
            self.assertIn("BOSS_BINDING_UNAVAILABLE", err)
            self.assertIn("Missing required model", err)

            # 4. Missing effort -> BLOCK (BOSS_BINDING_UNAVAILABLE)
            ok, err, _ = fixture_validator.validate_boss_binding("missing-effort-skill")
            self.assertFalse(ok)
            self.assertIn("BOSS_BINDING_UNAVAILABLE", err)
            self.assertIn("Missing required effort", err)

            # 5. Wrong model -> BLOCK (BOSS_BINDING_UNAVAILABLE)
            ok, err, _ = fixture_validator.validate_boss_binding("wrong-model-skill")
            self.assertFalse(ok)
            self.assertIn("BOSS_BINDING_UNAVAILABLE", err)
            self.assertIn("Model mismatch", err)

            # 6. Illegal effort -> BLOCK (BOSS_BINDING_UNAVAILABLE)
            ok, err, _ = fixture_validator.validate_boss_binding("illegal-effort-skill")
            self.assertFalse(ok)
            self.assertIn("BOSS_BINDING_UNAVAILABLE", err)
            self.assertIn("not in accepted_efforts", err)

            # 7. Effort above policy cap -> BLOCK (BOSS_BINDING_UNAVAILABLE)
            ok, err, _ = fixture_validator.validate_boss_binding("capped-effort-skill")
            self.assertFalse(ok)
            self.assertIn("BOSS_BINDING_UNAVAILABLE", err)
            self.assertIn("exceeds policy cap", err)
        finally:
            os.remove(temp_path)

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

    def test_host_spawn_request_requires_explicit_model_and_effort(self):
        spawn_schema = {
            "properties": {
                "model": {"type": "string"},
                "reasoning_effort": {"type": "string"},
                "task_name": {"type": "string"},
                "fork_turns": {"enum": ["none"]},
            }
        }
        spawn_request = {
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "task_name": "autoteam_boss_00_mission_1787106000",
            "fork_turns": "none",
        }
        ok, err = self.validator.validate_host_spawn_request(
            "SOL_HIGH",
            "gpt-5.6-sol",
            "high",
            spawn_schema,
            spawn_request,
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

        missing_model = dict(spawn_request)
        del missing_model["model"]
        ok, err = self.validator.validate_host_spawn_request(
            "SOL_HIGH",
            "gpt-5.6-sol",
            "high",
            spawn_schema,
            missing_model,
        )
        self.assertFalse(ok)
        self.assertIn("HOST_MODEL_BINDING_ERROR", err)
        self.assertIn("model", err)

        schema_without_override = {"properties": {"model": {"type": "string"}}}
        ok, err = self.validator.validate_host_spawn_request(
            "SOL_HIGH",
            "gpt-5.6-sol",
            "high",
            schema_without_override,
            spawn_request,
        )
        self.assertFalse(ok)
        self.assertIn("HOST_MODEL_BINDING_ERROR", err)
        self.assertIn("reasoning_effort", err)

        invalid_name = dict(spawn_request)
        invalid_name["task_name"] = "/root/autoteam_boss_20260831"
        ok, err = self.validator.validate_host_spawn_request(
            "SOL_HIGH",
            "gpt-5.6-sol",
            "high",
            spawn_schema,
            invalid_name,
        )
        self.assertFalse(ok)
        self.assertIn("HOST_AGENT_NAME_INVALID", err)

    def test_host_model_binding_rejects_inheritance_and_unproven_identity(self):
        ok, err = self.validator.validate_host_model_binding(
            "SOL_HIGH",
            "gpt-5.6-sol",
            "high",
            "gpt-5.6-luna",
            "high",
        )
        self.assertFalse(ok)
        self.assertIn("HOST_MODEL_BINDING_ERROR", err)
        self.assertIn("REJECT_CONTROLLER_MODEL_SUBSTITUTION", err)

        ok, err = self.validator.validate_host_model_binding(
            "GEMINI_FLASH_MEDIUM",
            "nine-router/ag/gemini-3.7-flash-medium",
            "medium",
            "UNPROVEN",
            "UNPROVEN",
        )
        self.assertFalse(ok)
        self.assertEqual(err, "HOST_MODEL_BINDING_ERROR: effective model is UNPROVEN")

    def test_host_model_binding_accepts_luna_root_to_sol_and_gemini_routes(self):
        ok, err = self.validator.validate_host_model_binding(
            "SOL_HIGH",
            "gpt-5.6-sol",
            "high",
            "gpt-5.6-sol",
            "high",
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

        ok, err = self.validator.validate_host_model_binding(
            "GEMINI_FLASH_MEDIUM",
            "nine-router/ag/gemini-3.7-flash-medium",
            "medium",
            "nine-router/ag/gemini-3.7-flash-medium",
            "medium",
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

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
        # Proves changing Core model in fixture alters validator behavior dynamically without modifying validator source
        # Endpoint ID GEMINI_FLASH_HIGH remains constant, but canonical model is changed to custom/changed-gemini-model
        custom_core = """```yaml
endpoints:
  - id: GEMINI_FLASH_HIGH
    family: gemini
    model: custom/changed-gemini-model
    accepted_efforts: [high]
```"""
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write(custom_core)
            temp_path = f.name
        try:
            custom_validator = PolicyValidator(core_path=temp_path)
            
            # 1. requested_model = old production Gemini model -> REJECT_REQUESTED_MODEL_MISMATCH
            ok, err = custom_validator.validate_controller_execution_binding(
                "GEMINI_FLASH_HIGH",
                "nine-router/ag/gemini-3.7-flash-high",
                "high",
                "GEMINI_FLASH_HIGH",
                "custom/changed-gemini-model",
                "high"
            )
            self.assertFalse(ok)
            self.assertIn("REJECT_REQUESTED_MODEL_MISMATCH", err)

            # 2. requested_model = custom/changed-gemini-model and actual_model = custom/changed-gemini-model -> PASS
            ok, err = custom_validator.validate_controller_execution_binding(
                "GEMINI_FLASH_HIGH",
                "custom/changed-gemini-model",
                "high",
                "GEMINI_FLASH_HIGH",
                "custom/changed-gemini-model",
                "high"
            )
            self.assertTrue(ok)
            self.assertIsNone(err)

            # 3. actual_model = old production model while endpoint ID is unchanged -> REJECT_CONTROLLER_MODEL_SUBSTITUTION
            ok, err = custom_validator.validate_controller_execution_binding(
                "GEMINI_FLASH_HIGH",
                "custom/changed-gemini-model",
                "high",
                "GEMINI_FLASH_HIGH",
                "nine-router/ag/gemini-3.7-flash-high",
                "high"
            )
            self.assertFalse(ok)
            self.assertIn("REJECT_CONTROLLER_MODEL_SUBSTITUTION", err)
        finally:
            os.remove(temp_path)

if __name__ == "__main__":
    unittest.main()
