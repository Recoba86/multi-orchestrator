"""Tests for Task 12: Live activation, master switch, declarative catalog, and rollback verification.

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§13.2)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 12)
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_boss_binding import legacy_binding, shadow_boss_binding
from core.runtime_endpoint_validator import RuntimeEndpointValidator
from core.runtime_reviewer_selector import select_reviewer
from core.runtime_role_dispatch import dispatch_role
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode, read_mode, write_mode
from core.runtime_routing_policy import RuntimePolicy, load_runtime_policy, weights_for
from core.runtime_routing_switch import (
    ROUTING_SWITCH_PATH_DEFAULT,
    is_routing_enabled,
    set_routing_enabled,
)
from core.runtime_weighted_selector import SelectionKey, weighted_select

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"
ORCHESTRATOR_ROUTING_CLI = REPO_ROOT / "scripts" / "orchestrator_routing.py"


class MasterSwitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.switch_path = Path(self.tmp.name) / "enabled.json"
        self.state_path = Path(self.tmp.name) / "mode.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_switch_defaults_to_false(self):
        self.assertFalse(is_routing_enabled(self.switch_path))

    def test_corrupt_switch_defaults_to_false(self):
        self.switch_path.parent.mkdir(parents=True, exist_ok=True)
        self.switch_path.write_text("{not json", encoding="utf-8")
        self.assertFalse(is_routing_enabled(self.switch_path))

    def test_on_and_off_persist_and_preserve_mode(self):
        write_mode(SOL_MODE, state_path=self.state_path)
        set_routing_enabled(True, path=self.switch_path)
        self.assertTrue(is_routing_enabled(self.switch_path))
        self.assertEqual(read_mode(self.state_path), SOL_MODE)

        set_routing_enabled(False, path=self.switch_path)
        self.assertFalse(is_routing_enabled(self.switch_path))
        self.assertEqual(read_mode(self.state_path), SOL_MODE)

        # Switch to GrokMode
        write_mode(GROK_MODE, state_path=self.state_path)
        set_routing_enabled(True, path=self.switch_path)
        self.assertTrue(is_routing_enabled(self.switch_path))
        self.assertEqual(read_mode(self.state_path), GROK_MODE)


class RuntimeEndpointCatalogTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.endpoint_validator = RuntimeEndpointValidator(runtime_policy=self.policy)

    def test_step_3_7_flash_is_runtime_valid(self):
        meta = self.policy.endpoint_resolution["STEP_3_7_FLASH"]
        self.assertTrue(meta.get("enabled", False))
        self.assertTrue(meta.get("verified", False))
        self.assertEqual(meta.get("eligibility"), "eligible")

        ok, err = self.endpoint_validator.validate_endpoint("STEP_3_7_FLASH", effort="high")
        self.assertTrue(ok, f"STEP_3_7_FLASH validation failed: {err}")

    def test_ox_alpha_is_disabled_and_unselectable(self):
        meta = self.policy.endpoint_resolution["OX_ALPHA"]
        self.assertFalse(meta.get("enabled", True))
        self.assertFalse(meta.get("verified", True))
        self.assertEqual(meta.get("eligibility"), "disabled")

        ok, err = self.endpoint_validator.validate_endpoint("OX_ALPHA")
        self.assertFalse(ok)
        self.assertIn("REJECT_DISABLED_ENDPOINT", err or "")

    def test_plus_luna_xhigh_remains_unverified(self):
        meta = self.policy.endpoint_resolution["PLUS_LUNA_XHIGH"]
        self.assertFalse(meta.get("verified", False))
        self.assertEqual(meta.get("eligibility"), "unverified")

        ok, err = self.endpoint_validator.validate_endpoint("PLUS_LUNA_XHIGH")
        self.assertFalse(ok)
        self.assertIn("REJECT_UNVERIFIED_ENDPOINT", err or "")

    def test_new_model_can_be_added_via_config_without_code_changes(self):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        raw["endpoint_resolution"]["CUSTOM_FAST_MODEL"] = {
            "model": "custom/fast-model-v1",
            "effort": "high",
            "enabled": True,
            "verified": True,
            "eligibility": "eligible",
        }
        raw["failure_domains"]["custom_pool"] = ["CUSTOM_FAST_MODEL"]
        raw["independence_groups"]["custom_pool"] = ["CUSTOM_FAST_MODEL"]
        raw["role_weights"]["SCOUT"]["SolMode"]["base"].append({
            "endpoint": "CUSTOM_FAST_MODEL",
            "weight": 10.0,
        })
        # rebalance SCOUT SolMode weights to 100
        raw["role_weights"]["SCOUT"]["SolMode"]["base"][0]["weight"] = 60.0

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
            yaml.safe_dump(raw, tf)
            temp_config = Path(tf.name)

        try:
            custom_policy = load_runtime_policy(temp_config)
            custom_validator = RuntimeEndpointValidator(runtime_policy=custom_policy)
            ok, err = custom_validator.validate_endpoint("CUSTOM_FAST_MODEL", effort="high")
            self.assertTrue(ok)

            # Route through existing selector
            key = SelectionKey(mission_id="custom-m", role="SCOUT", ordinal=0, mode=SOL_MODE)
            dec = dispatch_role(custom_policy, "SCOUT", key)
            self.assertIn(dec.selected_endpoint, custom_policy.endpoint_resolution)
        finally:
            temp_config.unlink(missing_ok=True)


class OrchestratorRoutingCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "mode.json"
        self.switch_path = Path(self.tmp.name) / "enabled.json"
        self.health_path = Path(self.tmp.name) / "health.json"
        self.telemetry_path = Path(self.tmp.name) / "telemetry.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _run_cli(self, *args) -> subprocess.CompletedProcess:
        cmd = [
            sys.executable,
            str(ORCHESTRATOR_ROUTING_CLI),
            "--state-path", str(self.state_path),
            "--switch-path", str(self.switch_path),
            "--health-path", str(self.health_path),
            "--telemetry-path", str(self.telemetry_path),
            *args,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)

    def test_status_command(self):
        res = self._run_cli("status")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Master Switch:", res.stdout)
        self.assertIn("Persistent Mode:", res.stdout)
        self.assertIn("Active Config Path:", res.stdout)

    def test_on_off_and_use_commands(self):
        # Default is OFF
        self.assertFalse(is_routing_enabled(self.switch_path))

        # on
        res = self._run_cli("on")
        self.assertEqual(res.returncode, 0)
        self.assertTrue(is_routing_enabled(self.switch_path))

        # off
        res = self._run_cli("off")
        self.assertEqual(res.returncode, 0)
        self.assertFalse(is_routing_enabled(self.switch_path))

        # use SolMode
        res = self._run_cli("use", "SolMode")
        self.assertEqual(res.returncode, 0)
        self.assertTrue(is_routing_enabled(self.switch_path))
        self.assertEqual(read_mode(self.state_path), SOL_MODE)

        # use GrokMode
        res = self._run_cli("use", "GrokMode")
        self.assertEqual(res.returncode, 0)
        self.assertTrue(is_routing_enabled(self.switch_path))
        self.assertEqual(read_mode(self.state_path), GROK_MODE)

    def test_models_and_validate_commands(self):
        res_models = self._run_cli("models")
        self.assertEqual(res_models.returncode, 0, res_models.stderr)
        self.assertIn("STEP_3_7_FLASH", res_models.stdout)
        self.assertIn("OX_ALPHA", res_models.stdout)

        res_val = self._run_cli("validate")
        self.assertEqual(res_val.returncode, 0, res_val.stderr)
        self.assertIn("[PASS]", res_val.stdout)
    def test_legacy_rollback_when_switch_is_off_versus_on(self):
        """Verify that when master switch is OFF, legacy wrapper bindings/chains are returned."""
        # 1. Switch OFF: Sol wrapper returns SOL_HIGH, Grok wrapper returns GROK_4_6_HIGH
        set_routing_enabled(False, path=self.switch_path)
        res_sol_off = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "route_model.py"),
             "--switch-path", str(self.switch_path),
             "--health-path", str(self.health_path),
             "--telemetry-path", str(self.telemetry_path),
             "select", "--no-telemetry", "--role", "BOSS", "--skill", "sol-luna-orchestrator-v2"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        self.assertEqual(res_sol_off.returncode, 0, res_sol_off.stderr)
        self.assertEqual(json.loads(res_sol_off.stdout)["selected_endpoint"], "SOL_HIGH")
        self.assertEqual(json.loads(res_sol_off.stdout)["routing_authority"], "LEGACY_WRAPPER_AUTHORITY")

        res_grok_off = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "route_model.py"),
             "--switch-path", str(self.switch_path),
             "--health-path", str(self.health_path),
             "--telemetry-path", str(self.telemetry_path),
             "select", "--no-telemetry", "--role", "BOSS", "--skill", "grok-orchestrator-v2"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        self.assertEqual(res_grok_off.returncode, 0, res_grok_off.stderr)
        self.assertEqual(json.loads(res_grok_off.stdout)["selected_endpoint"], "GROK_4_6_HIGH")
        self.assertEqual(json.loads(res_grok_off.stdout)["routing_authority"], "LEGACY_WRAPPER_AUTHORITY")

        # 2. Switch ON: Runtime mode-aware routing is used
        set_routing_enabled(True, path=self.switch_path)
        write_mode(GROK_MODE, state_path=self.state_path)
        res_on = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "route_model.py"),
             "--switch-path", str(self.switch_path),
             "--state-path", str(self.state_path),
             "--health-path", str(self.health_path),
             "--telemetry-path", str(self.telemetry_path),
             "select", "--no-telemetry", "--role", "BOSS", "--skill", "sol-luna-orchestrator-v2"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        self.assertEqual(res_on.returncode, 0, res_on.stderr)
        # In GrokMode with runtime routing ON, Boss is GROK_4_6_HIGH even if sol wrapper was queried
        self.assertEqual(json.loads(res_on.stdout)["selected_endpoint"], "GROK_4_6_HIGH")


if __name__ == "__main__":
    unittest.main()
