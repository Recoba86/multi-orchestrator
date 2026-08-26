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
    def test_grokmode_zero_gpt_plus_eligibility(self):
        policy = load_runtime_policy(CONFIG_PATH)
        gpt_plus_endpoints = set(policy.domains["gpt_plus"].endpoint_ids)
        for (role, mode, overlay), candidates in policy.role_weights.items():
            if mode == GROK_MODE:
                for c in candidates:
                    self.assertNotIn(
                        c.endpoint_id,
                        gpt_plus_endpoints,
                        f"GrokMode role {role} contains GPT Plus endpoint {c.endpoint_id}",
                    )
        for ep in policy.boss_chains[GROK_MODE]:
            self.assertNotIn(
                ep,
                gpt_plus_endpoints,
                f"GrokMode boss chain contains GPT Plus endpoint {ep}",
            )

    # -------------------------------------------------------------------------
    # G & H. Sol absent from Standard Worker and Deep Worker
    # -------------------------------------------------------------------------
    def test_sol_absent_from_workers(self):
        policy = load_runtime_policy(CONFIG_PATH)
        for (role, mode, overlay), candidates in policy.role_weights.items():
            if role in ("STANDARD_WORKER", "DEEP_WORKER"):
                for c in candidates:
                    self.assertNotEqual(
                        c.endpoint_id,
                        "SOL_HIGH",
                        f"SOL_HIGH found in {role} for mode {mode}",
                    )

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
            [("OX_ALPHA", 30.0), ("GEMINI_FLASH_HIGH", 35.0), ("PLUS_LUNA", 25.0), ("STEP_3_7_FLASH", 10.0)],
        )
        grok_overlay = weights_for(policy, "STANDARD_WORKER", GROK_MODE, True)
        self.assertEqual(
            [(c.endpoint_id, c.weight) for c in grok_overlay],
            [("OX_ALPHA", 30.0), ("GEMINI_FLASH_HIGH", 55.0), ("STEP_3_7_FLASH", 15.0)],
        )

    # -------------------------------------------------------------------------
    # M. GrokMode base worker exact 75/25
    # -------------------------------------------------------------------------
    def test_grokmode_base_worker_75_25(self):
        policy = load_runtime_policy(CONFIG_PATH)
        grok_base = weights_for(policy, "STANDARD_WORKER", GROK_MODE, False)
        self.assertEqual(
            [(c.endpoint_id, c.weight) for c in grok_base],
            [("GEMINI_FLASH_HIGH", 75.0), ("STEP_3_7_FLASH", 25.0)],
        )

    # -------------------------------------------------------------------------
    # N. GPT Plus shared failure domain contains Sol and applicable Luna
    # -------------------------------------------------------------------------
    def test_gpt_plus_shared_failure_domain(self):
        policy = load_runtime_policy(CONFIG_PATH)
        domain = policy.domains["gpt_plus"]
        self.assertEqual(
            set(domain.endpoint_ids),
            {"SOL_HIGH", "PLUS_LUNA", "PLUS_LUNA_XHIGH"},
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
    # P. Reviewer GPT-family independence rule
    # -------------------------------------------------------------------------
    def test_reviewer_gpt_family_independence(self):
        policy = load_runtime_policy(CONFIG_PATH)
        for mode in (SOL_MODE, GROK_MODE):
            row = policy.reviewer_tables.get(("gpt_family", mode))
            self.assertIsNotNone(row)
            for c in row:
                grp = group_of(policy, c.endpoint_id)
                self.assertNotEqual(
                    grp,
                    "gpt_family",
                    f"Reviewer table for gpt_family in {mode} contains gpt_family candidate {c.endpoint_id}",
                )

    # -------------------------------------------------------------------------
    # Boss chains
    # -------------------------------------------------------------------------
    def test_boss_chains(self):
        policy = load_runtime_policy(CONFIG_PATH)
        self.assertEqual(
            boss_chain_for(policy, SOL_MODE),
            ("SOL_HIGH", "GROK_4_6_HIGH", "OPUS_4_6_THINKING", "GEMINI_FLASH_HIGH"),
        )
        self.assertEqual(
            boss_chain_for(policy, GROK_MODE),
            ("GROK_4_6_HIGH", "OPUS_4_6_THINKING", "GEMINI_FLASH_HIGH"),
        )

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
            data["independence_groups"]["gpt_family"].append("CX_SOL")
        self._assert_validation_error(mod, "nine-router/cx")

    def test_rejects_duplicate_candidate_in_table(self):
        def mod(data):
            data["role_weights"]["SCOUT"]["SolMode"]["base"].append(
                {"endpoint": "GEMINI_FLASH_HIGH", "weight": 0.0}
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

    def test_rejects_gpt_plus_in_grokmode_boss(self):
        def mod(data):
            data["boss_chains"]["GrokMode"].append("SOL_HIGH")
        self._assert_validation_error(mod, "GrokMode")

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
