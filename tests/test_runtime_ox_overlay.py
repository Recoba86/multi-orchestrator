"""Tests for Task 6: Optional OX Standard Worker overlay and managed OX agent declaration.

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§5.4, §5.5, §10, §11)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 6)
"""

import collections
import copy
from pathlib import Path
import tempfile
import unittest
import tomllib
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_role_dispatch import (
    ALLOWED_ROLES,
    DispatchDecision,
    dispatch_role,
    select_for_role,
)
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import RuntimePolicy, load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"
OX_AGENT_TOML = REPO_ROOT / "agents" / "router-model-nine-router-ox-alpha.toml"


class OxWorkerOverlayTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    def _policy_with_ox_state(self, state: str) -> RuntimePolicy:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        raw["ox_overlay"] = state
        if state in ("enabled", "auto"):
            raw["endpoint_resolution"]["OX_ALPHA"]["enabled"] = True
            raw["endpoint_resolution"]["OX_ALPHA"]["verified"] = True
            raw["endpoint_resolution"]["OX_ALPHA"]["eligibility"] = "eligible"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
            yaml.safe_dump(raw, tf)
            temp_path = Path(tf.name)
        try:
            return load_runtime_policy(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

    def test_production_config_has_ox_disabled_and_unselectable(self):
        """Task 12: In production config, OX is disabled and unselectable."""
        key = SelectionKey(mission_id="prod-ox", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(self.policy, "STANDARD_WORKER", key, ox_runtime_eligible=True, validator=self.validator)
        self.assertEqual(dec.table_used, "base")
        self.assertNotIn("OX_ALPHA", dec.effective_candidates)
    # -------------------------------------------------------------------------
    # OVERLAY TABLE SELECTION: disabled / enabled / auto
    # -------------------------------------------------------------------------
    def test_disabled_solmode_worker_uses_base(self):
        policy = self._policy_with_ox_state("disabled")
        key = SelectionKey(mission_id="m-dis-sol", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, ox_runtime_eligible=True, validator=self.validator)
        self.assertEqual(dec.table_used, "base")
        self.assertNotIn("OX_ALPHA", dec.effective_candidates)

    def test_disabled_grokmode_worker_uses_base(self):
        policy = self._policy_with_ox_state("disabled")
        key = SelectionKey(mission_id="m-dis-grok", role="STANDARD_WORKER", ordinal=0, mode=GROK_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, ox_runtime_eligible=True, validator=self.validator)
        self.assertEqual(dec.table_used, "base")
        self.assertNotIn("OX_ALPHA", dec.effective_candidates)

    def test_enabled_solmode_worker_uses_overlay(self):
        policy = self._policy_with_ox_state("enabled")
        key = SelectionKey(mission_id="m-en-sol", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
        self.assertIn(dec.table_used, ("overlay", "ox_overlay"))
        self.assertIn("OX_ALPHA", dec.effective_candidates)

    def test_enabled_grokmode_worker_uses_overlay(self):
        policy = self._policy_with_ox_state("enabled")
        key = SelectionKey(mission_id="m-en-grok", role="STANDARD_WORKER", ordinal=0, mode=GROK_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
        self.assertIn(dec.table_used, ("overlay", "ox_overlay"))
        self.assertIn("OX_ALPHA", dec.effective_candidates)
        # GrokMode overlay must contain zero GPT Plus
        gpt_plus_eps = set(policy.domains["gpt_plus"].endpoint_ids)
        for ep in dec.effective_candidates:
            self.assertNotIn(ep, gpt_plus_eps)

    def test_auto_runtime_eligible_true_uses_overlay(self):
        policy = self._policy_with_ox_state("auto")
        key = SelectionKey(mission_id="m-auto-t", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, ox_runtime_eligible=True, validator=self.validator)
        self.assertIn(dec.table_used, ("overlay", "ox_overlay"))
        self.assertIn("OX_ALPHA", dec.effective_candidates)

    def test_auto_runtime_eligible_false_uses_base(self):
        policy = self._policy_with_ox_state("auto")
        key = SelectionKey(mission_id="m-auto-f", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, ox_runtime_eligible=False, validator=self.validator)
        self.assertEqual(dec.table_used, "base")
        self.assertNotIn("OX_ALPHA", dec.effective_candidates)

    def test_auto_runtime_eligible_none_uses_base(self):
        policy = self._policy_with_ox_state("auto")
        key = SelectionKey(mission_id="m-auto-n", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, ox_runtime_eligible=None, validator=self.validator)
        self.assertEqual(dec.table_used, "base")
        self.assertNotIn("OX_ALPHA", dec.effective_candidates)

    def test_auto_omitted_signal_defaults_to_base(self):
        policy = self._policy_with_ox_state("auto")
        key = SelectionKey(mission_id="m-auto-omit", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
        self.assertEqual(dec.table_used, "base")
        self.assertNotIn("OX_ALPHA", dec.effective_candidates)

    def test_domain_eligible_callable_support(self):
        policy = self._policy_with_ox_state("auto")
        key = SelectionKey(mission_id="m-callable", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec_active = dispatch_role(
            policy, "STANDARD_WORKER", key,
            domain_eligible=lambda dom: dom == "ox_combo",
            validator=self.validator,
        )
        self.assertIn(dec_active.table_used, ("overlay", "ox_overlay"))

        dec_inactive = dispatch_role(
            policy, "STANDARD_WORKER", key,
            domain_eligible=lambda dom: dom != "ox_combo",
            validator=self.validator,
        )
        self.assertEqual(dec_inactive.table_used, "base")

    # -------------------------------------------------------------------------
    # ROLE BOUNDARY: Non-worker roles unaffected by OX state
    # -------------------------------------------------------------------------
    def test_scout_unaffected_by_ox_state(self):
        for state in ("enabled", "disabled", "auto"):
            policy = self._policy_with_ox_state(state)
            key = SelectionKey(mission_id="m-scout-ox", role="SCOUT", ordinal=0, mode=SOL_MODE)
            dec = dispatch_role(policy, "SCOUT", key, ox_runtime_eligible=True, validator=self.validator)
            self.assertEqual(dec.table_used, "base")
            self.assertNotIn("OX_ALPHA", dec.effective_candidates)

    def test_deep_worker_unaffected_by_ox_state(self):
        for state in ("enabled", "disabled", "auto"):
            policy = self._policy_with_ox_state(state)
            key = SelectionKey(mission_id="m-deep-ox", role="DEEP_WORKER", ordinal=0, mode=SOL_MODE)
            dec = dispatch_role(policy, "DEEP_WORKER", key, ox_runtime_eligible=True, validator=self.validator)
            self.assertEqual(dec.table_used, "base")
            self.assertNotIn("OX_ALPHA", dec.effective_candidates)

    # -------------------------------------------------------------------------
    # DISTRIBUTION WITH OVERLAY ACTIVE
    # -------------------------------------------------------------------------
    def test_solmode_ox_overlay_distribution_30_35_25_10(self):
        policy = self._policy_with_ox_state("enabled")
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="dist-sol-ox", role="STANDARD_WORKER", ordinal=i, mode=SOL_MODE)
            dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
            counts[dec.endpoint_id] += 1

        self.assertAlmostEqual(counts["OX_ALPHA"] / n, 0.30, delta=0.02)
        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.35, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.25, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.10, delta=0.02)

    def test_grokmode_ox_overlay_distribution_30_55_15(self):
        policy = self._policy_with_ox_state("enabled")
        counts = collections.Counter()
        n = 5000
        for i in range(n):
            key = SelectionKey(mission_id="dist-grok-ox", role="STANDARD_WORKER", ordinal=i, mode=GROK_MODE)
            dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
            counts[dec.endpoint_id] += 1

        self.assertAlmostEqual(counts["OX_ALPHA"] / n, 0.30, delta=0.02)
        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.55, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.15, delta=0.02)
        self.assertEqual(counts["PLUS_LUNA"], 0)
        self.assertEqual(counts["SOL_HIGH"], 0)

    # -------------------------------------------------------------------------
    # STATIC INELIGIBILITY: Falls back to BASE table before selection
    # -------------------------------------------------------------------------
    def test_static_ineligibility_falls_back_to_base_table(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        raw["ox_overlay"] = "enabled"
        raw["endpoint_resolution"]["OX_ALPHA"]["verified"] = False
        raw["endpoint_resolution"]["OX_ALPHA"]["eligibility"] = "unverified"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
            yaml.safe_dump(raw, tf)
            temp_path = Path(tf.name)
        try:
            policy = load_runtime_policy(temp_path)
            key = SelectionKey(mission_id="static-inelig", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
            dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
            self.assertEqual(dec.table_used, "base")
            self.assertNotIn("OX_ALPHA", dec.effective_candidates)
        finally:
            temp_path.unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # EXPLICIT EXCLUSION PRESERVES OVERLAY TABLE
    # -------------------------------------------------------------------------
    def test_explicit_exclusion_preserves_overlay_table(self):
        policy = self._policy_with_ox_state("enabled")
        key = SelectionKey(mission_id="excl-ox", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(
            policy,
            "STANDARD_WORKER",
            key,
            excluded_endpoints={"OX_ALPHA"},
            validator=self.validator,
        )
        self.assertIn(dec.table_used, ("overlay", "ox_overlay"))
        self.assertNotEqual(dec.endpoint_id, "OX_ALPHA")
        self.assertIn("OX_ALPHA", dec.excluded_endpoints)

    # -------------------------------------------------------------------------
    # DETERMINISTIC OX SELECTION & CORE REJECTION (NO REROLL)
    # -------------------------------------------------------------------------
    def test_deterministic_ox_selection_and_core_rejection_no_reroll(self):
        policy = self._policy_with_ox_state("enabled")
        # Isolate OX_ALPHA selection by excluding all other candidates
        key = SelectionKey(mission_id="ox-select-key", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(
            policy,
            "STANDARD_WORKER",
            key,
            excluded_endpoints={"GEMINI_FLASH_HIGH", "PLUS_LUNA", "STEP_3_7_FLASH"},
            validator=self.validator,
        )
        self.assertEqual(dec.endpoint_id, "OX_ALPHA")
        self.assertEqual(dec.model, "nine-router/OX-ALpha")
        self.assertEqual(dec.effort, "default")
        self.assertEqual(dec.failure_domain, "ox_combo")
        self.assertEqual(dec.independence_group, "ox_combo")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")


class OxAgentDeclarationTests(unittest.TestCase):
    def test_ox_agent_toml_is_removed_from_active_payload(self):
        """Task 12: OX managed agent TOML must be removed from active installer payload."""
        self.assertFalse(OX_AGENT_TOML.exists(), f"OX agent {OX_AGENT_TOML} should not exist in active payload")

if __name__ == "__main__":
    unittest.main()
