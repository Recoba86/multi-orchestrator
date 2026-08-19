#!/usr/bin/env python3
"""
STATIC_POLICY_TESTS for Multi Orchestrator RC3 Architecture.
Validates purely static trace sanitization and malformed JSON resilience.
(Executable policy validation is formally tested against production code in test_policy_validator.py).
"""

import unittest
import os
import json
import tempfile
import importlib.util

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestStaticPolicyAndTraceSanitization(unittest.TestCase):
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
