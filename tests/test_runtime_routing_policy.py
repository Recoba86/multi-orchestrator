"""Tests for runtime routing policy parsing and validation (Task 2)."""

import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import (
    CandidateWeight,
    FailureDomain,
    PolicyValidationError,
    RuntimePolicy,
    boss_chain_for,
    group_of,
    load_runtime_policy,
    weights_for,
)

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(CONFIG_PATH.exists(), f"Missing config file at {CONFIG_PATH}")
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            self.raw_yaml = yaml.safe_load(f)

    def _load_modified(self, modifier) -> RuntimePolicy:
        data = copy.deepcopy(self.raw_yaml)
        modifier(data)
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
            yaml.safe_dump(data, tf)
            temp_path = Path(tf.name)
        try:
            return load_runtime_policy(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _assert_validation_error(self, modifier, substring: str | None = None):
        with self.assertRaises(PolicyValidationError) as ctx:
            self._load_modified(modifier)
        msg = str(ctx.exception)
        self.assertTrue(
            msg.startswith("INVALID_RUNTIME_POLICY: "),
            f"Error message must start with prefix 'INVALID_RUNTIME_POLICY: ', got {msg!r}",
        )
        if substring:
            self.assertIn(substring, msg)

    # -------------------------------------------------------------------------
    # A. Canonical shipped runtime-routing.yaml loads successfully
    # -------------------------------------------------------------------------
    def test_canonical_shipped_config_loads_successfully(self):
        policy = load_runtime_policy(CONFIG_PATH)
        self.assertIsInstance(policy, RuntimePolicy)

    # -------------------------------------------------------------------------
    # B & C. SolMode and GrokMode sections recognized via RoutingMode
    # -------------------------------------------------------------------------
    def test_mode_sections_recognized(self):
        policy = load_runtime_policy(CONFIG_PATH)
        self.assertIn(SOL_MODE, policy.boss_chains)
        self.assertIn(GROK_MODE, policy.boss_chains)
        self.assertIn(("SCOUT", SOL_MODE, False), policy.role_weights)
        self.assertIn(("SCOUT", GROK_MODE, False), policy.role_weights)

    # -------------------------------------------------------------------------
    # D. Every weighted table sums exactly to 100
    # -------------------------------------------------------------------------
    def test_every_role_weight_table_sums_to_100(self):
        policy = load_runtime_policy(CONFIG_PATH)
        for (role, mode, overlay), candidates in policy.role_weights.items():
            total = sum(c.weight for c in candidates)
            self.assertTrue(
                math.isclose(total, 100.0, abs_tol=1e-9),
                f"Role table {role}/{mode}/overlay={overlay} sums to {total}, expected 100",
            )
        for (grp, mode), candidates in policy.reviewer_tables.items():
            total = sum(c.weight for c in candidates)
            self.assertTrue(
                math.isclose(total, 100.0, abs_tol=1e-9),
                f"Reviewer table {grp}/{mode} sums to {total}, expected 100",
            )

    # -------------------------------------------------------------------------
    # E. Global targets sum exactly to 100
    # -------------------------------------------------------------------------
    def test_global_targets_sum_to_100_and_match_spec(self):
        policy = load_runtime_policy(CONFIG_PATH)
        total = sum(policy.global_targets.values())
        self.assertTrue(math.isclose(total, 100.0, abs_tol=1e-9))
        self.assertEqual(
            policy.global_targets,
            {
                "gemini": 45.0,
                "supergrok": 25.0,
                "gpt_plus": 17.0,
                "cheap": 7.0,
                "opus": 6.0,
            },
        )

    # -------------------------------------------------------------------------
    # F. GrokMode contains zero GPT Plus eligibility
    # -------------------------------------------------------------------------
    def test_modes_preserve_canonical_role_policy(self):
        policy = load_runtime_policy(CONFIG_PATH)
        expected = {
            "BOSS": [("SOL_HIGH", "gpt-5.6-sol", "high"), ("GROK_4_6_HIGH", "nine-router/gcli/grok-4.6-high", "high"), ("GROK_CURSOR_HIGH", "nine-router/cu/cursor-grok-4.6-high", "high")],
            "SCOUT": [("GEMINI_FLASH_MEDIUM", "nine-router/ag/gemini-3.7-flash-medium", "medium"), ("QWEN_3_8_FLASH", "commandcode/qwen3.8-flash", "high")],
            "STANDARD_WORKER": [("GEMINI_FLASH_HIGH", "nine-router/ag/gemini-3.7-flash-high", "high"), ("PLUS_LUNA", "gpt-5.6-luna", "max")],
            "DEEP_WORKER": [("GROK_4_6_HIGH", "nine-router/gcli/grok-4.6-high", "high"), ("GEMINI_FLASH_HIGH", "nine-router/ag/gemini-3.7-flash-high", "high"), ("SOL_HIGH", "gpt-5.6-sol", "high")],
            "VERIFIER": [("SOL_HIGH", "gpt-5.6-sol", "high"), ("GROK_4_6_HIGH", "nine-router/gcli/grok-4.6-high", "high"), ("OPUS_COMBO", "nine-router/Opus", "high"), ("GEMINI_FLASH_HIGH", "nine-router/ag/gemini-3.7-flash-high", "high")],
            "PREMIUM_SECOND_OPINION": [("OPUS_COMBO", "nine-router/Opus", "high"), ("PLUS_TERRA", "gpt-5.6-terra", "high")],
        }
        for role, entries in expected.items():
            self.assertEqual(
                [(item.endpoint_id, item.model, item.effort) for item in policy.operator_policy[role]],
                entries,
            )
        self.assertEqual(boss_chain_for(policy, SOL_MODE), boss_chain_for(policy, GROK_MODE))
        for role in ("SCOUT", "STANDARD_WORKER", "DEEP_WORKER"):
            self.assertEqual(
                weights_for(policy, role, SOL_MODE, False),
                weights_for(policy, role, GROK_MODE, False),
            )
    # -------------------------------------------------------------------------
    def test_standard_worker_excludes_sol_but_deep_worker_allows_canonical_sol(self):
        policy = load_runtime_policy(CONFIG_PATH)
        for (role, mode, overlay), candidates in policy.role_weights.items():
            if role == "STANDARD_WORKER":
                self.assertNotIn("SOL_HIGH", [c.endpoint_id for c in candidates])
            if role == "DEEP_WORKER" and not overlay:
                self.assertIn("SOL_HIGH", [c.endpoint_id for c in candidates])
    # -------------------------------------------------------------------------
    # I. Scout forbidden-model invariant (no Sol, Grok, Opus)
    # -------------------------------------------------------------------------
    def test_scout_forbidden_models(self):
        policy = load_runtime_policy(CONFIG_PATH)
        forbidden_groups = {"supergrok", "opus"}
        forbidden_endpoints = {"SOL_HIGH"}
        for (role, mode, overlay), candidates in policy.role_weights.items():
            if role == "SCOUT":
                for c in candidates:
                    self.assertNotIn(c.endpoint_id, forbidden_endpoints)
                    grp = group_of(policy, c.endpoint_id)
                    self.assertNotIn(grp, forbidden_groups)

    # -------------------------------------------------------------------------
    # J, K, L. OX overlay exact identity and weights
    # -------------------------------------------------------------------------
    def test_ox_exact_identity_and_weights(self):
        policy = load_runtime_policy(CONFIG_PATH)
        self.assertEqual(
            policy.endpoint_resolution["OX_ALPHA"]["model"],
            "nine-router/OX-ALpha",
        )
        self.assertEqual(
            policy.endpoint_resolution["OX_ALPHA"]["effort"],
            "default",
        )
        sol_overlay = weights_for(policy, "STANDARD_WORKER", SOL_MODE, True)
        self.assertEqual(
            [(c.endpoint_id, c.weight) for c in sol_overlay],
            [("OX_ALPHA", 30.0), ("GEMINI_FLASH_HIGH", 70.0)],
        )
        grok_overlay = weights_for(policy, "STANDARD_WORKER", GROK_MODE, True)
        self.assertEqual(
            [(c.endpoint_id, c.weight) for c in grok_overlay],
            [("OX_ALPHA", 30.0), ("GEMINI_FLASH_HIGH", 70.0)],
        )

    # -------------------------------------------------------------------------
    # M. Both modes translate to the same Standard Worker chain
    # -------------------------------------------------------------------------
    def test_grokmode_base_worker_100(self):
        policy = load_runtime_policy(CONFIG_PATH)
        grok_base = weights_for(policy, "STANDARD_WORKER", GROK_MODE, False)
        self.assertEqual(
            [(c.endpoint_id, c.weight) for c in grok_base],
            [("GEMINI_FLASH_HIGH", 100.0), ("PLUS_LUNA", 0.0)],
        )

    # -------------------------------------------------------------------------
    # N. GPT Plus shared failure domain contains Sol and applicable Luna
    # -------------------------------------------------------------------------
    def test_gpt_plus_shared_failure_domain(self):
        policy = load_runtime_policy(CONFIG_PATH)
        domain = policy.domains["gpt_plus"]
        self.assertEqual(
            set(domain.endpoint_ids),
            {"SOL_HIGH", "PLUS_LUNA", "PLUS_LUNA_XHIGH", "PLUS_TERRA"},
        )

    # -------------------------------------------------------------------------
    # O. Luna xhigh remains not selectable/unverified
    # -------------------------------------------------------------------------
    def test_luna_xhigh_unverified_metadata(self):
        policy = load_runtime_policy(CONFIG_PATH)
        resolution = policy.endpoint_resolution["PLUS_LUNA_XHIGH"]
        self.assertFalse(resolution.get("verified", False))
        self.assertEqual(resolution.get("eligibility"), "unverified")

    # -------------------------------------------------------------------------
    # P. Common Reviewer / Verifier chain is independent of mode
    # -------------------------------------------------------------------------
    def test_reviewer_common_chain_is_mode_independent(self):
        policy = load_runtime_policy(CONFIG_PATH)
        expected = (
            CandidateWeight("SOL_HIGH", 100.0),
            CandidateWeight("GROK_4_6_HIGH", 0.0),
            CandidateWeight("OPUS_COMBO", 0.0),
            CandidateWeight("GEMINI_FLASH_HIGH", 0.0),
        )
        for mode in (SOL_MODE, GROK_MODE):
            self.assertEqual(policy.reviewer_tables[("sol_family", mode)], expected)

    # -------------------------------------------------------------------------
    # Boss chains
    # -------------------------------------------------------------------------
    def test_boss_chains(self):
        policy = load_runtime_policy(CONFIG_PATH)
        expected = ("SOL_HIGH", "GROK_4_6_HIGH", "GROK_CURSOR_HIGH")
        self.assertEqual(boss_chain_for(policy, SOL_MODE), expected)
        self.assertEqual(boss_chain_for(policy, GROK_MODE), expected)

    # -------------------------------------------------------------------------
    # Static Validation & Error Cases
    # -------------------------------------------------------------------------
    def test_rejects_table_sum_not_100(self):
        def mod(data):
            data["role_weights"]["SCOUT"]["SolMode"]["base"][0]["weight"] = 69.0
        self._assert_validation_error(mod, "sum")

    def test_rejects_negative_weight(self):
        def mod(data):
            data["role_weights"]["SCOUT"]["SolMode"]["base"][0]["weight"] = -10.0
            data["role_weights"]["SCOUT"]["SolMode"]["base"][1]["weight"] = 100.0
        self._assert_validation_error(mod, "negative")

    def test_rejects_bool_as_weight(self):
        def mod(data):
            data["role_weights"]["SCOUT"]["SolMode"]["base"][0]["weight"] = True
        self._assert_validation_error(mod, "boolean")

    def test_rejects_unknown_mode_name(self):
        def mod(data):
            data["boss_chains"]["sol_mode"] = data["boss_chains"].pop("SolMode")
        self._assert_validation_error(mod, "mode")

    def test_rejects_unknown_endpoint(self):
        def mod(data):
            data["boss_chains"]["SolMode"].append("UNKNOWN_ENDPOINT")
        self._assert_validation_error(mod, "UNKNOWN_ENDPOINT")

    def test_rejects_nine_router_cx_models(self):
        def mod(data):
            data["endpoint_resolution"]["CX_SOL"] = {
                "model": "nine-router/cx/gpt-5.6-sol",
                "effort": "high",
                "verified": True,
            }
            data["independence_groups"]["sol_family"].append("CX_SOL")
        self._assert_validation_error(mod, "nine-router/cx")

    def test_rejects_duplicate_candidate_in_table(self):
        def mod(data):
            data["role_weights"]["SCOUT"]["SolMode"]["base"].append(
                {"endpoint": "GEMINI_FLASH_MEDIUM", "weight": 0.0}
            )
        self._assert_validation_error(mod, "duplicate")

    def test_rejects_invalid_ox_overlay_state(self):
        def mod(data):
            data["ox_overlay"] = "banana"
        self._assert_validation_error(mod, "ox_overlay")

    def test_rejects_sol_in_standard_worker(self):
        def mod(data):
            data["role_weights"]["STANDARD_WORKER"]["SolMode"]["base"].append(
                {"endpoint": "SOL_HIGH", "weight": 0.0}
            )
        self._assert_validation_error(mod, "SOL_HIGH")

    def test_rejects_grok_in_scout(self):
        def mod(data):
            data["role_weights"]["SCOUT"]["SolMode"]["base"].append(
                {"endpoint": "GROK_4_6_HIGH", "weight": 0.0}
            )
        self._assert_validation_error(mod, "SCOUT")

    def test_rejects_divergent_grokmode_boss_chain(self):
        def mod(data):
            data["boss_chains"]["GrokMode"].append("SOL_HIGH")
        self._assert_validation_error(mod, "BOSS")

    def test_rejects_luna_xhigh_marked_verified(self):
        def mod(data):
            data["endpoint_resolution"]["PLUS_LUNA_XHIGH"]["verified"] = True
            data["endpoint_resolution"]["PLUS_LUNA_XHIGH"]["eligibility"] = "eligible"
        self._assert_validation_error(mod, "PLUS_LUNA_XHIGH")

    def test_rejects_extra_top_level_keys(self):
        def mod(data):
            data["unexpected_extra_key"] = 123
        self._assert_validation_error(mod, "unknown top-level key")


if __name__ == "__main__":
    unittest.main()
