"""OX overlay is opportunistic primary-first, not a 30% roll."""

from pathlib import Path
import sys
import tempfile
import unittest

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_routing_mode import GROK_MODE, SOL_MODE
from core.policy_validator import PolicyValidator
from core.runtime_role_dispatch import dispatch_role
from core.runtime_routing_policy import load_runtime_policy, weights_for
from core.runtime_weighted_selector import SelectionKey, weighted_select

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class OxWorkerOverlayTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    def _policy_with_ox_state(self, state: str, *, ready: bool = True):
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        raw["ox_overlay"] = state
        if state in ("enabled", "auto") and ready:
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

    def test_overlay_disabled_in_shipped_config(self):
        self.assertEqual(self.policy.ox_overlay, "disabled")

    def test_production_config_has_ox_disabled_and_unselectable(self):
        for mode in (SOL_MODE, GROK_MODE):
            key = SelectionKey(mission_id="prod-ox", role="STANDARD_WORKER", ordinal=0, mode=mode)
            dec = dispatch_role(
                self.policy,
                "STANDARD_WORKER",
                key,
                ox_runtime_eligible=True,
                validator=self.validator,
            )
            self.assertEqual(dec.table_used, "base")
            self.assertNotIn("OX_ALPHA", dec.effective_candidates)

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
        self.assertEqual(dec.table_used, "overlay")
        self.assertIn("OX_ALPHA", dec.effective_candidates)

    def test_enabled_grokmode_worker_uses_overlay(self):
        policy = self._policy_with_ox_state("enabled")
        key = SelectionKey(mission_id="m-en-grok", role="STANDARD_WORKER", ordinal=0, mode=GROK_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
        self.assertEqual(dec.table_used, "overlay")
        self.assertIn("OX_ALPHA", dec.effective_candidates)

    def test_auto_runtime_eligible_true_uses_overlay(self):
        policy = self._policy_with_ox_state("auto")
        key = SelectionKey(mission_id="m-auto-t", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, ox_runtime_eligible=True, validator=self.validator)
        self.assertEqual(dec.table_used, "overlay")
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
        active = dispatch_role(
            policy,
            "STANDARD_WORKER",
            key,
            domain_eligible=lambda domain: domain == "ox_combo",
            validator=self.validator,
        )
        inactive = dispatch_role(
            policy,
            "STANDARD_WORKER",
            key,
            domain_eligible=lambda domain: domain != "ox_combo",
            validator=self.validator,
        )
        self.assertEqual(active.table_used, "overlay")
        self.assertEqual(inactive.table_used, "base")

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

    def test_solmode_overlay_table_order(self):
        row = weights_for(self.policy, "STANDARD_WORKER", SOL_MODE, True)
        self.assertEqual([c.endpoint_id for c in row], ["OX_ALPHA", "GEMINI_FLASH_HIGH"])

    def test_overlay_selects_first_eligible_not_distribution(self):
        row = weights_for(self.policy, "STANDARD_WORKER", SOL_MODE, True)
        key = SelectionKey(mission_id="ox", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        # OX is disabled/unverified in catalog so select_candidate would skip it;
        # raw weighted_select on overlay order still prefers first non-excluded.
        res = weighted_select(row, key, exclude={"OX_ALPHA"})
        self.assertEqual(res.selected_endpoint, "GEMINI_FLASH_HIGH")

    def test_static_ineligibility_falls_back_to_base_table(self):
        policy = self._policy_with_ox_state("enabled", ready=False)
        key = SelectionKey(mission_id="static-inelig", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)
        dec = dispatch_role(policy, "STANDARD_WORKER", key, validator=self.validator)
        self.assertEqual(dec.table_used, "base")
        self.assertNotIn("OX_ALPHA", dec.effective_candidates)

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
        self.assertEqual(dec.table_used, "overlay")
        self.assertNotEqual(dec.endpoint_id, "OX_ALPHA")
        self.assertIn("OX_ALPHA", dec.excluded_endpoints)

    def test_deterministic_ox_selection_and_core_rejection_no_reroll(self):
        policy = self._policy_with_ox_state("enabled")
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

    def test_ox_agent_toml_is_removed_from_active_payload(self):
        self.assertFalse(
            (REPO_ROOT / "agents" / "router-model-nine-router-ox-alpha.toml").exists()
        )


if __name__ == "__main__":
    unittest.main()
