"""Tests for Task 8: Failure-Domain Health and Configurable Cooldown.

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§3, §5, §10)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 8)
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import yaml
REPO_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_boss_binding import shadow_boss_binding
from core.runtime_reviewer_selector import select_reviewer
from core.runtime_role_dispatch import dispatch_role
from core.runtime_routing_health import (
    DEFAULT_COOLDOWN_SECONDS,
    HEALTH_STATE_PATH_DEFAULT,
    DomainHealthState,
    FailureKind,
    clear_health,
    domain_eligible,
    domain_of_endpoint,
    excluded_domains,
    excluded_endpoints,
    load_health_state,
    record_failure,
)
from core.runtime_routing_mode import GROK_MODE, SOL_MODE
from core.runtime_routing_policy import RuntimePolicy, load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class FailureDomainHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.health_path = Path(self.tmp_dir.name) / "runtime-routing" / "health.json"
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    def tearDown(self):
        self.tmp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. DOMAIN MAPPING (Endpoint -> Failure Domain from policy)
    # -------------------------------------------------------------------------
    def test_domain_mapping_from_policy(self):
        self.assertEqual(domain_of_endpoint(self.policy, "SOL_HIGH"), "gpt_plus")
        self.assertEqual(domain_of_endpoint(self.policy, "PLUS_LUNA"), "gpt_plus")
        self.assertEqual(domain_of_endpoint(self.policy, "PLUS_LUNA_XHIGH"), "gpt_plus")
        self.assertEqual(domain_of_endpoint(self.policy, "GEMINI_FLASH_HIGH"), "gemini")
        self.assertEqual(domain_of_endpoint(self.policy, "GROK_4_6_HIGH"), "supergrok")
        self.assertEqual(domain_of_endpoint(self.policy, "OPUS_COMBO"), "opus")
        self.assertEqual(domain_of_endpoint(self.policy, "STEP_3_7_FLASH"), "cheap")
        self.assertEqual(domain_of_endpoint(self.policy, "OX_ALPHA"), "ox_combo")

    def test_unknown_endpoint_domain_mapping_fails_closed(self):
        with self.assertRaises(ValueError):
            domain_of_endpoint(self.policy, "UNKNOWN_EP")

    # -------------------------------------------------------------------------
    # 2. COOLDOWN CONFIGURATION & TIME BOUNDARIES
    # -------------------------------------------------------------------------
    def test_default_cooldown_is_1800_seconds(self):
        self.assertEqual(DEFAULT_COOLDOWN_SECONDS, 1800)

    def test_exact_time_boundary_cooldown(self):
        t0 = 1000000
        # Initially healthy
        self.assertTrue(domain_eligible("gpt_plus", now=t0, path=self.health_path, policy=self.policy))

        # Record quota exhaustion at t0
        record_failure(
            domain="gpt_plus",
            failure_kind=FailureKind.QUOTA_EXHAUSTED,
            now=t0,
            cooldown_seconds=1800,
            path=self.health_path,
            policy=self.policy,
        )

        # Before expiry: unhealthy
        self.assertFalse(domain_eligible("gpt_plus", now=t0 + 100, path=self.health_path, policy=self.policy))
        self.assertFalse(domain_eligible("gpt_plus", now=t0 + 1799, path=self.health_path, policy=self.policy))

        # Exactly at expiry (t0 + 1800): healthy
        self.assertTrue(domain_eligible("gpt_plus", now=t0 + 1800, path=self.health_path, policy=self.policy))

        # After expiry: healthy
        self.assertTrue(domain_eligible("gpt_plus", now=t0 + 1801, path=self.health_path, policy=self.policy))

    def test_repeated_failure_extends_cooldown_deterministically(self):
        t0 = 1000000
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=t0, cooldown_seconds=1800, path=self.health_path, policy=self.policy)
        # Second failure at t0 + 1000 extends cooldown to (t0 + 1000) + 1800 = t0 + 2800
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=t0 + 1000, cooldown_seconds=1800, path=self.health_path, policy=self.policy)

        self.assertFalse(domain_eligible("gpt_plus", now=t0 + 1800, path=self.health_path, policy=self.policy))
        self.assertFalse(domain_eligible("gpt_plus", now=t0 + 2799, path=self.health_path, policy=self.policy))
        self.assertTrue(domain_eligible("gpt_plus", now=t0 + 2800, path=self.health_path, policy=self.policy))

    def test_repeated_failure_never_shortens_cooldown(self):
        t0 = 1000000
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=t0, cooldown_seconds=1800, path=self.health_path, policy=self.policy)
        # Failure with shorter cooldown cannot shorten existing expiry
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=t0 + 100, cooldown_seconds=500, path=self.health_path, policy=self.policy)
        self.assertFalse(domain_eligible("gpt_plus", now=t0 + 1799, path=self.health_path, policy=self.policy))
        self.assertTrue(domain_eligible("gpt_plus", now=t0 + 1800, path=self.health_path, policy=self.policy))

    # -------------------------------------------------------------------------
    # 3. QUALIFYING FAILURE KINDS
    # -------------------------------------------------------------------------
    def test_qualifying_failure_kinds(self):
        t0 = 1000000
        for kind in (FailureKind.HTTP_429, FailureKind.HTTP_503, FailureKind.TIMEOUT, FailureKind.QUOTA_EXHAUSTED):
            clear_health(path=self.health_path)
            record_failure("supergrok", kind, now=t0, path=self.health_path, policy=self.policy)
            self.assertFalse(domain_eligible("supergrok", now=t0 + 1, path=self.health_path, policy=self.policy))

    def test_unsupported_failure_kind_rejected(self):
        t0 = 1000000
        with self.assertRaises(ValueError):
            record_failure("supergrok", "UNSUPPORTED_ERROR", now=t0, path=self.health_path, policy=self.policy)

    # -------------------------------------------------------------------------
    # 4. GPT_PLUS SHARED CAPACITY DOMAIN SUPPRESSION
    # -------------------------------------------------------------------------
    def test_gpt_plus_shared_domain_suppression(self):
        t0 = 1000000
        # SOL_HIGH quota failure suppresses all gpt_plus endpoints
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=t0, path=self.health_path, policy=self.policy)
        excl = excluded_endpoints(self.policy, now=t0 + 1, path=self.health_path)
        self.assertIn("SOL_HIGH", excl)
        self.assertIn("PLUS_LUNA", excl)
        self.assertIn("PLUS_LUNA_XHIGH", excl)
        self.assertNotIn("GEMINI_FLASH_HIGH", excl)
        self.assertNotIn("GROK_4_6_HIGH", excl)

    # -------------------------------------------------------------------------
    # 5. OX COMBO COOLDOWN (429 / 503 / Timeout)
    # -------------------------------------------------------------------------
    def test_ox_combo_failures_suppress_ox_combo_domain(self):
        t0 = 1000000
        for kind in (FailureKind.HTTP_429, FailureKind.HTTP_503, FailureKind.TIMEOUT):
            clear_health(path=self.health_path)
            record_failure("ox_combo", kind, now=t0, path=self.health_path, policy=self.policy)
            self.assertFalse(domain_eligible("ox_combo", now=t0 + 10, path=self.health_path, policy=self.policy))
            excl = excluded_endpoints(self.policy, now=t0 + 10, path=self.health_path)
            self.assertIn("OX_ALPHA", excl)
            self.assertTrue(domain_eligible("ox_combo", now=t0 + 1800, path=self.health_path, policy=self.policy))

    # -------------------------------------------------------------------------
    # 6. UNRELATED DOMAIN ISOLATION
    # -------------------------------------------------------------------------
    def test_unrelated_domain_isolation(self):
        t0 = 1000000
        record_failure("gemini", FailureKind.HTTP_503, now=t0, path=self.health_path, policy=self.policy)
        self.assertFalse(domain_eligible("gemini", now=t0 + 1, path=self.health_path, policy=self.policy))
        self.assertTrue(domain_eligible("supergrok", now=t0 + 1, path=self.health_path, policy=self.policy))
        self.assertTrue(domain_eligible("gpt_plus", now=t0 + 1, path=self.health_path, policy=self.policy))
        self.assertTrue(domain_eligible("opus", now=t0 + 1, path=self.health_path, policy=self.policy))
        self.assertTrue(domain_eligible("cheap", now=t0 + 1, path=self.health_path, policy=self.policy))
        self.assertTrue(domain_eligible("ox_combo", now=t0 + 1, path=self.health_path, policy=self.policy))

    # -------------------------------------------------------------------------
    # 7. PERSISTENCE, ZERO MUTATION ON READ, PERMISSIONS & SYMLINK SAFETY
    # -------------------------------------------------------------------------
    def test_zero_mutation_on_read_and_missing_file(self):
        non_existent = Path(self.tmp_dir.name) / "deep" / "missing" / "health.json"
        self.assertTrue(domain_eligible("gpt_plus", now=100, path=non_existent, policy=self.policy))
        self.assertEqual(excluded_domains(now=100, path=non_existent), ())
        self.assertEqual(excluded_endpoints(self.policy, now=100, path=non_existent), ())
        self.assertFalse(non_existent.exists())
        self.assertFalse(non_existent.parent.exists())

    def test_atomic_write_and_restrictive_permissions(self):
        t0 = 1000000
        record_failure("supergrok", FailureKind.HTTP_429, now=t0, path=self.health_path, policy=self.policy)
        self.assertTrue(self.health_path.exists())
        mode_bits = stat.S_IMODE(os.stat(self.health_path).st_mode)
        self.assertEqual(mode_bits, 0o600)

    def test_symlink_refusal_on_write_and_read(self):
        t0 = 1000000
        target = self.health_path.parent / "innocent.json"
        self.health_path.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")
        self.health_path.symlink_to(target)

        # Read refuses symlink -> fail closed (treat as healthy default or empty without mutation)
        self.assertTrue(domain_eligible("supergrok", now=t0, path=self.health_path, policy=self.policy))

        # Write refuses symlink -> RuntimeError
        with self.assertRaises(RuntimeError):
            record_failure("supergrok", FailureKind.HTTP_429, now=t0, path=self.health_path, policy=self.policy)

    def test_default_now_none_clock_path(self):
        """Calling health functions with now=None must not raise NameError."""
        self.assertTrue(domain_eligible("gemini", now=None, path=self.health_path, policy=self.policy))
        record_failure("gemini", FailureKind.HTTP_429, now=None, path=self.health_path, policy=self.policy)
        self.assertFalse(domain_eligible("gemini", now=None, path=self.health_path, policy=self.policy))
        excl = excluded_domains(now=None, path=self.health_path)
        self.assertIn("gemini", excl)
        eps = excluded_endpoints(self.policy, now=None, path=self.health_path)
        self.assertIn("GEMINI_FLASH_HIGH", eps)
    # -------------------------------------------------------------------------
    # 8. SHADOW INTEGRATION: BOSS BINDING (Task 4)
    # -------------------------------------------------------------------------
    def test_solmode_boss_under_gpt_plus_cooldown(self):
        t0 = 1000000
        # Healthy: selects SOL_HIGH
        dec_healthy = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            domain_eligible=lambda dom: domain_eligible(dom, now=t0, path=self.health_path, policy=self.policy),
            validator=self.validator,
        )
        self.assertEqual(dec_healthy.selected_endpoint, "SOL_HIGH")

        # Quota failure on gpt_plus
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=t0, path=self.health_path, policy=self.policy)

        # In cooldown: selects GROK_4_6_HIGH
        dec_cooldown = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            domain_eligible=lambda dom: domain_eligible(dom, now=t0 + 10, path=self.health_path, policy=self.policy),
            validator=self.validator,
        )
        self.assertEqual(dec_cooldown.selected_endpoint, "GROK_4_6_HIGH")
        self.assertEqual(dec_cooldown.mode, SOL_MODE)  # Mode is NOT changed!

        # After expiry: selects SOL_HIGH again
        dec_expired = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            domain_eligible=lambda dom: domain_eligible(dom, now=t0 + 1800, path=self.health_path, policy=self.policy),
            validator=self.validator,
        )
        self.assertEqual(dec_expired.selected_endpoint, "SOL_HIGH")

    # -------------------------------------------------------------------------
    # 9. SHADOW INTEGRATION: WORKER & OX AUTO (Tasks 5 & 6)
    # -------------------------------------------------------------------------
    def test_worker_and_ox_auto_under_cooldown(self):
        t0 = 1000000
        key = SelectionKey(mission_id="ox-health", role="STANDARD_WORKER", ordinal=0, mode=SOL_MODE)

        # Load policy fixture with ox_overlay=auto and OX_ALPHA eligible
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        raw["ox_overlay"] = "auto"
        raw["endpoint_resolution"]["OX_ALPHA"]["enabled"] = True
        raw["endpoint_resolution"]["OX_ALPHA"]["verified"] = True
        raw["endpoint_resolution"]["OX_ALPHA"]["eligibility"] = "eligible"
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
            yaml.safe_dump(raw, tf)
            tf_path = Path(tf.name)

        try:
            auto_policy = load_runtime_policy(tf_path)

            # Initially healthy auto -> overlay table used
            dec_init = dispatch_role(
                auto_policy, "STANDARD_WORKER", key,
                domain_eligible=lambda dom: domain_eligible(dom, now=t0, path=self.health_path, policy=auto_policy),
                validator=self.validator,
            )
            self.assertEqual(dec_init.table_used, "overlay")

            # OX 503 error
            record_failure("ox_combo", FailureKind.HTTP_503, now=t0, path=self.health_path, policy=auto_policy)

            # In cooldown -> base table used
            dec_cool = dispatch_role(
                auto_policy, "STANDARD_WORKER", key,
                domain_eligible=lambda dom: domain_eligible(dom, now=t0 + 10, path=self.health_path, policy=auto_policy),
                validator=self.validator,
            )
            self.assertEqual(dec_cool.table_used, "base")

            # After expiry -> overlay table used again
            dec_exp = dispatch_role(
                auto_policy, "STANDARD_WORKER", key,
                domain_eligible=lambda dom: domain_eligible(dom, now=t0 + 1800, path=self.health_path, policy=auto_policy),
                validator=self.validator,
            )
            self.assertEqual(dec_exp.table_used, "overlay")
        finally:
            tf_path.unlink(missing_ok=True)
    # -------------------------------------------------------------------------
    # 10. SHADOW INTEGRATION: REVIEWER HEALTH FILTERING (Task 7)
    # -------------------------------------------------------------------------
    def test_reviewer_under_gpt_plus_cooldown(self):
        t0 = 1000000
        key = SelectionKey(mission_id="rev-health", role="VERIFIER", ordinal=0, mode=SOL_MODE)

        # Gemini implementer in SolMode: table is Grok 60, Luna 25, Opus 15
        record_failure("gpt_plus", FailureKind.QUOTA_EXHAUSTED, now=t0, path=self.health_path, policy=self.policy)

        # Reviewer selection under gpt_plus cooldown excludes Luna
        dec = select_reviewer(
            self.policy, "GEMINI_FLASH_HIGH", key,
            domain_eligible=lambda dom: domain_eligible(dom, now=t0 + 10, path=self.health_path, policy=self.policy),
            validator=self.validator,
        )
        self.assertNotIn("PLUS_LUNA", dec.effective_candidates)
        self.assertNotEqual(dec.selected_endpoint, "PLUS_LUNA")

    # -------------------------------------------------------------------------
    # 11. STATIC GUARD: NO write_mode IMPORT
    # -------------------------------------------------------------------------
    def test_static_guard_no_write_mode_import(self):
        src_path = REPO_ROOT / "core" / "runtime_routing_health.py"
        if src_path.exists():
            content = src_path.read_text(encoding="utf-8")
            self.assertNotIn("write_mode", content)


if __name__ == "__main__":
    unittest.main()
