"""Tests for Task 9: Routing Telemetry, Target-Share Report, and Shadow Controller CLI.

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§4, §8)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 9)
"""

from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode, write_mode
from core.runtime_routing_policy import RuntimePolicy, load_runtime_policy
from core.runtime_routing_health import FailureKind, record_failure
from core.runtime_routing_telemetry import (
    TELEMETRY_SCHEMA_VERSION,
    TELEMETRY_PATH_DEFAULT,
    RoutingEvent,
    TargetShareReport,
    aggregate_telemetry,
    append_routing_event,
    read_telemetry_events,
)

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"
CLI_PATH = REPO_ROOT / "scripts" / "route_model.py"


class RoutingTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.telemetry_path = Path(self.tmp_dir.name) / "runtime-routing" / "routing-telemetry.jsonl"
        self.policy = load_runtime_policy(CONFIG_PATH)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _sample_event(self, **kwargs) -> RoutingEvent:
        defaults = {
            "timestamp_utc": "2026-08-26T12:00:00Z",
            "mode": "SolMode",
            "role": "STANDARD_WORKER",
            "endpoint_id": "GEMINI_FLASH_HIGH",
            "endpoint_independence_group": "gemini",
            "capacity_domain": "gemini",
            "model": "nine-router/ag/gemini-3.7-flash-high",
            "effort": "high",
            "core_validation_status": "REQUEST_VALID",
            "table_used": "base",
            "mission_id": "m-sample",
            "ordinal": 0,
            "bucket": 150,
            "algorithm_version": 1,
            "excluded_unverified": (),
            "implementer_independence_group": None,
            "decision_reason": "Selected candidate",
        }
        defaults.update(kwargs)
        return RoutingEvent(**defaults)

    # -------------------------------------------------------------------------
    # 1. TELEMETRY STORAGE & APPEND ROUND-TRIP (JSONL)
    # -------------------------------------------------------------------------
    def test_append_and_read_single_event(self):
        event = self._sample_event()
        append_routing_event(event, path=self.telemetry_path)
        self.assertTrue(self.telemetry_path.exists())

        events, malformed_count = read_telemetry_events(path=self.telemetry_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(malformed_count, 0)
        self.assertEqual(events[0].endpoint_id, "GEMINI_FLASH_HIGH")
        self.assertEqual(events[0].mode, "SolMode")
        self.assertEqual(events[0].bucket, 150)

    def test_multiple_appends_preserve_order_and_history(self):
        e1 = self._sample_event(ordinal=0, endpoint_id="GEMINI_FLASH_HIGH")
        e2 = self._sample_event(ordinal=1, endpoint_id="PLUS_LUNA", capacity_domain="gpt_plus", endpoint_independence_group="gpt_family")
        e3 = self._sample_event(ordinal=2, endpoint_id="OX_ALPHA", capacity_domain="ox_combo", endpoint_independence_group="ox_combo", table_used="overlay")

        append_routing_event(e1, path=self.telemetry_path)
        append_routing_event(e2, path=self.telemetry_path)
        append_routing_event(e3, path=self.telemetry_path)

        events, malformed = read_telemetry_events(path=self.telemetry_path)
        self.assertEqual(len(events), 3)
        self.assertEqual(malformed, 0)
        self.assertEqual([ev.ordinal for ev in events], [0, 1, 2])
        self.assertEqual([ev.endpoint_id for ev in events], ["GEMINI_FLASH_HIGH", "PLUS_LUNA", "OX_ALPHA"])

    # -------------------------------------------------------------------------
    # 2. WRITE SAFETY: 0600 PERMISSIONS & SYMLINK REFUSAL
    # -------------------------------------------------------------------------
    def test_telemetry_file_permissions_and_symlink_refusal(self):
        event = self._sample_event()
        append_routing_event(event, path=self.telemetry_path)
        mode_bits = stat.S_IMODE(os.stat(self.telemetry_path).st_mode)
        self.assertEqual(mode_bits, 0o600)

        # Symlink refusal
        symlink_path = Path(self.tmp_dir.name) / "symlink_telemetry.jsonl"
        target_file = Path(self.tmp_dir.name) / "target.txt"
        target_file.write_text("initial", encoding="utf-8")
        symlink_path.symlink_to(target_file)

        with self.assertRaises(RuntimeError):
            append_routing_event(event, path=symlink_path)
        self.assertEqual(target_file.read_text(encoding="utf-8"), "initial")

    # -------------------------------------------------------------------------
    # 3. PRIVACY: NO PROMPTS/RESPONSES/SECRETS; SANITIZATION APPLIED
    # -------------------------------------------------------------------------
    def test_sanitization_and_privacy_guarantees(self):
        event = self._sample_event(mission_id="mission\nwith\x00control\rchars")
        append_routing_event(event, path=self.telemetry_path)
        raw_lines = self.telemetry_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(raw_lines), 1)
        data = json.loads(raw_lines[0])
        # Ensure newlines and control characters are stripped from identifiers
        self.assertNotIn("\n", data["mission_id"])
        self.assertNotIn("\r", data["mission_id"])
        # Ensure no prompt, response, or secret keys exist in the record schema
        forbidden_keys = {"prompt", "response", "tool_payload", "api_key", "secret", "authorization", "password"}
        self.assertFalse(any(k in data for k in forbidden_keys))

    # -------------------------------------------------------------------------
    # 4. MALFORMED ROWS HANDLING
    # -------------------------------------------------------------------------
    def test_malformed_jsonl_rows_handled_gracefully(self):
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        valid_row = json.dumps({
            "version": TELEMETRY_SCHEMA_VERSION,
            "timestamp_utc": "2026-08-26T12:00:00Z",
            "mode": "SolMode",
            "role": "SCOUT",
            "endpoint_id": "GEMINI_FLASH_HIGH",
            "capacity_domain": "gemini",
            "endpoint_independence_group": "gemini",
            "model": "nine-router/ag/gemini-3.7-flash-high",
            "effort": "high",
            "core_validation_status": "REQUEST_VALID",
            "table_used": "base",
            "mission_id": "m1",
            "ordinal": 0,
            "bucket": 10,
            "algorithm_version": 1,
            "excluded_unverified": [],
            "implementer_independence_group": None,
            "decision_reason": "ok",
        })
        self.telemetry_path.write_text(f"{valid_row}\n{{not json\n{valid_row}\n{{\"version\": 99}}\n", encoding="utf-8")

        events, malformed = read_telemetry_events(path=self.telemetry_path)
        self.assertEqual(len(events), 2)
        self.assertEqual(malformed, 2)

    # -------------------------------------------------------------------------
    # 5. TARGET-SHARE REPORT: 45/25/17/7/6 & SEPARATE OX ACCOUNTING
    # -------------------------------------------------------------------------
    def test_target_share_report_calculation(self):
        # Synthetic distribution:
        # gemini: 45 events
        # supergrok: 25 events
        # gpt_plus: 17 events
        # cheap: 7 events
        # opus: 6 events
        # Total permanent = 100 events
        # ox_combo: 20 events (separate overlay)
        # Total dispatches = 120
        events = []
        for _ in range(45):
            events.append(self._sample_event(capacity_domain="gemini", endpoint_id="GEMINI_FLASH_HIGH"))
        for _ in range(25):
            events.append(self._sample_event(capacity_domain="supergrok", endpoint_id="GROK_4_6_HIGH"))
        for _ in range(17):
            events.append(self._sample_event(capacity_domain="gpt_plus", endpoint_id="PLUS_LUNA"))
        for _ in range(7):
            events.append(self._sample_event(capacity_domain="cheap", endpoint_id="STEP_3_7_FLASH"))
        for _ in range(6):
            events.append(self._sample_event(capacity_domain="opus", endpoint_id="OPUS_4_6_THINKING"))
        for _ in range(20):
            events.append(self._sample_event(capacity_domain="ox_combo", endpoint_id="OX_ALPHA", table_used="overlay"))

        for ev in events:
            append_routing_event(ev, path=self.telemetry_path)

        report = aggregate_telemetry(path=self.telemetry_path, policy=self.policy)
        self.assertIsInstance(report, TargetShareReport)
        self.assertEqual(report.total_permanent_dispatches, 100)
        self.assertEqual(report.total_all_dispatches, 120)

        # Permanent target checks: observed shares match exactly
        self.assertAlmostEqual(report.domain_shares["gemini"]["observed_pct"], 45.0)
        self.assertAlmostEqual(report.domain_shares["gemini"]["target_pct"], 45.0)
        self.assertAlmostEqual(report.domain_shares["gemini"]["delta_pct"], 0.0)

        self.assertAlmostEqual(report.domain_shares["supergrok"]["observed_pct"], 25.0)
        self.assertAlmostEqual(report.domain_shares["gpt_plus"]["observed_pct"], 17.0)
        self.assertAlmostEqual(report.domain_shares["cheap"]["observed_pct"], 7.0)
        self.assertAlmostEqual(report.domain_shares["opus"]["observed_pct"], 6.0)

        # OX accounting check: 20 out of 120 total dispatches
        self.assertEqual(report.ox_stats["count"], 20)
        self.assertAlmostEqual(report.ox_stats["share_of_all_dispatches_pct"], 20.0 / 120.0 * 100.0)

    # -------------------------------------------------------------------------
    # 6. TIME WINDOW FILTERING
    # -------------------------------------------------------------------------
    def test_window_filtering_in_aggregation(self):
        t_now = datetime.now(timezone.utc)
        t_old = t_now - timedelta(hours=48)

        e_old = self._sample_event(timestamp_utc=t_old.isoformat(), capacity_domain="gemini")
        e_new = self._sample_event(timestamp_utc=t_now.isoformat(), capacity_domain="supergrok")

        append_routing_event(e_old, path=self.telemetry_path)
        append_routing_event(e_new, path=self.telemetry_path)

        # 24h window excludes the 48h-old event
        report = aggregate_telemetry(path=self.telemetry_path, policy=self.policy, window=timedelta(hours=24), now=t_now)
        self.assertEqual(report.total_permanent_dispatches, 1)
        self.assertEqual(report.domain_shares["supergrok"]["count"], 1)
        self.assertEqual(report.domain_shares["gemini"]["count"], 0)

    # -------------------------------------------------------------------------
    # 7. TELEMETRY IS NOT CONTROL FLOW: WRITE FAILURE DOES NOT ALTER SELECTION
    # -------------------------------------------------------------------------
    def test_telemetry_write_failure_does_not_change_selection(self):
        code = (
            "from pathlib import Path; import sys; "
            "REPO_ROOT = Path('.').resolve(); sys.path.insert(0, str(REPO_ROOT)); "
            "from core.runtime_routing_policy import load_runtime_policy; "
            "from core.runtime_routing_mode import SOL_MODE; "
            "from core.runtime_weighted_selector import SelectionKey; "
            "from core.runtime_role_dispatch import dispatch_role; "
            "policy = load_runtime_policy(REPO_ROOT / 'config' / 'runtime-routing.yaml'); "
            "key = SelectionKey(mission_id='ctrl-flow', role='SCOUT', ordinal=0, mode=SOL_MODE); "
            "dec = dispatch_role(policy, 'SCOUT', key); "
            "print(dec.selected_endpoint)"
        )
        out = subprocess.check_output([sys.executable, "-c", code], cwd=REPO_ROOT, text=True).strip()
        self.assertEqual(out, "GEMINI_FLASH_HIGH")


class ShadowControllerCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp_dir.name) / "mode.json"
        self.switch_path = Path(self.tmp_dir.name) / "enabled.json"
        self.health_path = Path(self.tmp_dir.name) / "health.json"
        self.telemetry_path = Path(self.tmp_dir.name) / "telemetry.jsonl"
        self.policy = load_runtime_policy(CONFIG_PATH)
        # Enable routing switch for active selection telemetry tests
        self.switch_path.parent.mkdir(parents=True, exist_ok=True)
        self.switch_path.write_text(json.dumps({"version": 1, "enabled": True}), encoding="utf-8")

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _run_cli(self, *args) -> subprocess.CompletedProcess:
        cmd = [
            sys.executable,
            str(CLI_PATH),
            "--state-path", str(self.state_path),
            "--switch-path", str(self.switch_path),
            "--health-path", str(self.health_path),
            "--telemetry-path", str(self.telemetry_path),
            *args,
        ]
        return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
        res = self._run_cli("select", "--role", "SCOUT", "--mission-id", "m1", "--ordinal", "0")
        self.assertEqual(res.returncode, 0, f"CLI failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data["role"], "SCOUT")
        self.assertEqual(data["mode"], "SolMode")
        self.assertEqual(data["selected_endpoint"], "GEMINI_FLASH_HIGH")
        self.assertEqual(data["model"], "nine-router/ag/gemini-3.7-flash-high")
        self.assertEqual(data["effort"], "high")
        self.assertEqual(data["core_validation_status"], "REQUEST_VALID")

        # Verify telemetry event was appended
        events, _ = read_telemetry_events(self.telemetry_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].endpoint_id, "GEMINI_FLASH_HIGH")

    def test_cli_select_boss_grokmode(self):
        # Set mode to GrokMode
        write_mode(GROK_MODE, state_path=self.state_path)
        res = self._run_cli("select", "--role", "BOSS", "--mission-id", "m1", "--ordinal", "0")
        self.assertEqual(res.returncode, 0, f"CLI failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data["role"], "BOSS")
        self.assertEqual(data["mode"], "GrokMode")
        self.assertEqual(data["selected_endpoint"], "GROK_4_6_HIGH")
        events, _ = read_telemetry_events(self.telemetry_path)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].endpoint_id, "GROK_4_6_HIGH")
        self.assertEqual(events[0].endpoint_independence_group, "supergrok")
        self.assertEqual(events[0].capacity_domain, "supergrok")

    def test_cli_select_reviewer_solmode_with_sol_implementer(self):
        res = self._run_cli(
            "select",
            "--role", "VERIFIER",
            "--implementer", "SOL_HIGH",
            "--mission-id", "m1",
            "--ordinal", "0",
        )
        self.assertEqual(res.returncode, 0, f"CLI failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data["role"], "VERIFIER")
        self.assertEqual(data["implementer_endpoint"], "SOL_HIGH")
        self.assertEqual(data["implementer_independence_group"], "gpt_family")
        self.assertNotIn(data["selected_endpoint"], ("SOL_HIGH", "PLUS_LUNA", "PLUS_LUNA_XHIGH"))

    def test_cli_select_with_gpt_plus_cooldown(self):
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=1000, path=self.health_path, policy=self.policy)
        res = self._run_cli("select", "--role", "BOSS", "--mission-id", "m1", "--now", "1010")
        self.assertEqual(res.returncode, 0, f"CLI failed: {res.stderr}")
        data = json.loads(res.stdout)
        self.assertEqual(data["selected_endpoint"], "GROK_4_6_HIGH")
        self.assertEqual(data["mode"], "SolMode")  # Mode was not modified!

    # -------------------------------------------------------------------------
    # CLI: REPORT COMMAND
    # -------------------------------------------------------------------------
    def test_cli_report_output_format(self):
        # Generate some telemetry
        self._run_cli("select", "--role", "SCOUT", "--mission-id", "m1", "--ordinal", "0")
        self._run_cli("select", "--role", "STANDARD_WORKER", "--mission-id", "m1", "--ordinal", "1")
        res = self._run_cli("report")
        self.assertEqual(res.returncode, 0, f"CLI report failed: {res.stderr}")
        self.assertIn("Permanent Target Domains", res.stdout)
        self.assertIn("gemini", res.stdout)
        self.assertIn("supergrok", res.stdout)
        self.assertIn("ox_combo", res.stdout)


if __name__ == "__main__":
    unittest.main()
