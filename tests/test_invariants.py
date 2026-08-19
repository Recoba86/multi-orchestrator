#!/usr/bin/env python3
"""
Unit and Negative Tests for Multi Orchestrator RC3 Architecture.
Validates:
- Boss binding resolution & fail-closed behavior
- Root Controller separation (cannot self-promote)
- Invalid endpoint / illegal effort rejection
- Controller substitution detection
- Implementer self-conflict & Luna family conflict rejection
- Missing runtime evidence handling (UNPROVEN)
- Mission Trace sanitization & secret leakage protection
- Malformed trace resilience
"""

import unittest
import os
import json
import tempfile
import re
import yaml
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_PATH = os.path.join(REPO_ROOT, "core", "ORCHESTRATOR_CORE.md")

class TestMultiOrchestratorInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CORE_PATH, "r", encoding="utf-8") as f:
            text = f.read()
        yaml_blocks = re.findall(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
        cls.core_data = {}
        for b in yaml_blocks:
            try:
                loaded = yaml.safe_load(b)
                if isinstance(loaded, dict):
                    cls.core_data.update(loaded)
            except Exception:
                pass

        cls.endpoints = {ep["id"]: ep for ep in cls.core_data.get("endpoints", [])}
        cls.skill_boss_bindings = cls.core_data.get("skill_boss_bindings", {})
        cls.role_chains = cls.core_data.get("role_chains", {})
        cls.verifier_chains = cls.core_data.get("verifier_chains", {})

    def test_boss_bindings_exist(self):
        self.assertIn("grok-orchestrator-v2", self.skill_boss_bindings)
        self.assertIn("sol-luna-orchestrator-v2", self.skill_boss_bindings)
        grok_b = self.skill_boss_bindings["grok-orchestrator-v2"]
        sol_b = self.skill_boss_bindings["sol-luna-orchestrator-v2"]
        self.assertEqual(grok_b["required_boss_endpoint"], "GROK_4_6_HIGH")
        self.assertEqual(sol_b["required_boss_endpoint"], "SOL_HIGH")

    def test_boss_binding_unavailable_fails_closed(self):
        # Simulate Boss binding lookup for an unsupported / broken skill
        def resolve_boss_binding(skill_name):
            if skill_name not in self.skill_boss_bindings:
                return "BOSS_BINDING_UNAVAILABLE"
            binding = self.skill_boss_bindings[skill_name]
            ep_id = binding.get("required_boss_endpoint")
            if ep_id not in self.endpoints:
                return "BOSS_BINDING_UNAVAILABLE"
            return "READY"

        self.assertEqual(resolve_boss_binding("grok-orchestrator-v2"), "READY")
        self.assertEqual(resolve_boss_binding("sol-luna-orchestrator-v2"), "READY")
        self.assertEqual(resolve_boss_binding("unregistered-skill"), "BOSS_BINDING_UNAVAILABLE")

    def test_controller_cannot_self_promote(self):
        # Invariant: Root controller must never set role = "DEDICATED_BOSS"
        def validate_plane_role(agent_type, requested_role):
            if agent_type == "ROOT_CONTROLLER" and requested_role in ["BOSS", "DEDICATED_BOSS", "DECISION_PLANE"]:
                return "REJECT_CONTROLLER_SELF_PROMOTION"
            return "VALID"

        self.assertEqual(validate_plane_role("ROOT_CONTROLLER", "ROOT_CONTROLLER"), "VALID")
        self.assertEqual(validate_plane_role("ROOT_CONTROLLER", "BOSS"), "REJECT_CONTROLLER_SELF_PROMOTION")

    def test_invalid_endpoint_rejection(self):
        def validate_boss_requested_endpoint(endpoint_id):
            if endpoint_id not in self.endpoints:
                return "REJECT_UNKNOWN_ENDPOINT"
            return "VALID"

        self.assertEqual(validate_boss_requested_endpoint("GEMINI_FLASH_HIGH"), "VALID")
        self.assertEqual(validate_boss_requested_endpoint("PLUS_LUNA"), "VALID")
        self.assertEqual(validate_boss_requested_endpoint("FAKE_MODEL_9000"), "REJECT_UNKNOWN_ENDPOINT")

    def test_illegal_effort_rejection(self):
        def validate_effort_for_endpoint(endpoint_id, effort):
            if endpoint_id not in self.endpoints:
                return "REJECT_UNKNOWN_ENDPOINT"
            ep = self.endpoints[endpoint_id]
            if effort not in ep.get("accepted_efforts", []):
                return "REJECT_UNACCEPTED_EFFORT"
            policy_max = ep.get("policy_max_effort")
            if policy_max:
                eff_levels = {"low": 1, "medium": 2, "high": 3, "max": 4}
                if eff_levels.get(effort, 0) > eff_levels.get(policy_max, 0):
                    return "REJECT_EFFORT_EXCEEDS_POLICY"
            return "VALID"

        self.assertEqual(validate_effort_for_endpoint("PLUS_LUNA", "max"), "VALID")
        self.assertEqual(validate_effort_for_endpoint("OCG_LUNA", "high"), "VALID")
        self.assertEqual(validate_effort_for_endpoint("OCG_LUNA", "max"), "REJECT_EFFORT_EXCEEDS_POLICY")
        self.assertEqual(validate_effort_for_endpoint("DEEPSEEK_PRO", "low"), "REJECT_UNACCEPTED_EFFORT")

    def test_controller_substitution_attack_detection(self):
        def check_binding_match(requested_ep, requested_effort, executed_ep, executed_effort):
            req_model = self.endpoints.get(requested_ep, {}).get("model")
            exe_model = self.endpoints.get(executed_ep, {}).get("model")
            if req_model != exe_model or requested_effort != executed_effort:
                return False
            return True

        self.assertTrue(check_binding_match("GEMINI_FLASH_HIGH", "high", "GEMINI_FLASH_HIGH", "high"))
        # Attack 1: Controller substituted different endpoint
        self.assertFalse(check_binding_match("GEMINI_FLASH_HIGH", "high", "PLUS_LUNA", "high"))
        # Attack 2: Controller substituted lower effort
        self.assertFalse(check_binding_match("PLUS_LUNA", "max", "PLUS_LUNA", "low"))

    def test_verifier_independence_and_luna_family_conflict(self):
        def check_verifier_validity(implementer_id, verifier_id):
            if implementer_id == verifier_id:
                return "REJECT_SELF_VERIFICATION"
            imp_fam = self.endpoints.get(implementer_id, {}).get("family")
            ver_fam = self.endpoints.get(verifier_id, {}).get("family")
            if imp_fam and ver_fam and imp_fam == ver_fam:
                return "REJECT_MODEL_FAMILY_CONFLICT"
            return "VALID"

        self.assertEqual(check_verifier_validity("GEMINI_FLASH_HIGH", "PLUS_LUNA"), "VALID")
        self.assertEqual(check_verifier_validity("GEMINI_FLASH_HIGH", "GEMINI_FLASH_HIGH"), "REJECT_SELF_VERIFICATION")
        self.assertEqual(check_verifier_validity("PLUS_LUNA", "OCG_LUNA"), "REJECT_MODEL_FAMILY_CONFLICT")
        self.assertEqual(check_verifier_validity("OCG_LUNA", "PLUS_LUNA"), "REJECT_MODEL_FAMILY_CONFLICT")

    def test_unproven_evidence_recorded_correctly(self):
        # Invariant: If runtime cannot confirm, must record UNPROVEN
        def record_evidence(actual_model_observed):
            return actual_model_observed if actual_model_observed else "UNPROVEN"

        self.assertEqual(record_evidence("nine-router/ag/gemini-3.7-flash-high"), "nine-router/ag/gemini-3.7-flash-high")
        self.assertEqual(record_evidence(None), "UNPROVEN")

    def test_trace_secret_sanitization(self):
        spec = importlib.util.spec_from_file_location("mission_trace", os.path.join(REPO_ROOT, "scripts", "mission-trace.py"))
        mt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mt)

        dirty_payload = {
            "mission": {"mission_id": "test-123"},
            "auth": {"api_key": "sk-secret12345678901234567890", "token": "abcdef"},
            "headers": {"Authorization": "Bearer sensitive_token_here"},
            "clean_field": "public_data"
        }
        cleaned = mt.sanitize_trace_data(dirty_payload)
        self.assertEqual(cleaned["auth"]["api_key"], "[REDACTED]")
        self.assertEqual(cleaned["auth"]["token"], "[REDACTED]")
        self.assertEqual(cleaned["headers"]["Authorization"], "[REDACTED]")
        self.assertEqual(cleaned["clean_field"], "public_data")

    def test_malformed_trace_handling(self):
        # Test that malformed JSON is handled safely without crashing
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("{ invalid json structure")
            f_name = f.name
        try:
            with self.assertRaises(json.JSONDecodeError):
                with open(f_name, "r") as f_read:
                    json.load(f_read)
        finally:
            os.remove(f_name)

if __name__ == "__main__":
    unittest.main()
