"""Parallel capacity must replicate the healthy primary, not consume fallbacks."""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_adaptive_scheduler import AdaptiveScheduler, ScheduledTask
from core.runtime_reviewer_selector import select_reviewer
from core.runtime_role_dispatch import dispatch_role
from core.runtime_routing_mode import SOL_MODE
from core.runtime_routing_policy import load_runtime_policy
from core.runtime_weighted_selector import SelectionKey

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class ConcurrencyFallbackSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.scheduler = AdaptiveScheduler(self.policy)

    def test_multiple_parallel_scouts_use_same_healthy_primary(self):
        self.assertTrue(self.scheduler.dispatch(ScheduledTask("scout-1", "SCOUT")))
        self.assertTrue(self.scheduler.dispatch(ScheduledTask("scout-2", "SCOUT")))
        k0 = SelectionKey("m-scout-parallel", "SCOUT", 0, SOL_MODE)
        k1 = SelectionKey("m-scout-parallel", "SCOUT", 1, SOL_MODE)
        self.assertEqual(dispatch_role(self.policy, "SCOUT", k0).endpoint_id, "GEMINI_FLASH_MEDIUM")
        self.assertEqual(dispatch_role(self.policy, "SCOUT", k1).endpoint_id, "GEMINI_FLASH_MEDIUM")

    def test_multiple_parallel_workers_use_same_healthy_primary(self):
        self.assertTrue(self.scheduler.dispatch(ScheduledTask("w1", "STANDARD_WORKER", owned_files=("a.py",))))
        self.assertTrue(self.scheduler.dispatch(ScheduledTask("w2", "STANDARD_WORKER", owned_files=("b.py",))))
        k0 = SelectionKey("m-w", "STANDARD_WORKER", 0, SOL_MODE)
        k1 = SelectionKey("m-w", "STANDARD_WORKER", 1, SOL_MODE)
        self.assertEqual(dispatch_role(self.policy, "STANDARD_WORKER", k0).endpoint_id, "GEMINI_FLASH_HIGH")
        self.assertEqual(dispatch_role(self.policy, "STANDARD_WORKER", k1).endpoint_id, "GEMINI_FLASH_HIGH")

    def test_fallback_activates_on_genuine_primary_unavailability(self):
        k0 = SelectionKey("m-fail", "SCOUT", 0, SOL_MODE)
        dec = dispatch_role(self.policy, "SCOUT", k0, excluded_endpoints={"GEMINI_FLASH_MEDIUM"})
        self.assertEqual(dec.endpoint_id, "QWEN_3_8_FLASH")

    def test_reviewer_gemini_to_sol_and_sol_to_grok(self):
        k0 = SelectionKey("m-rev", "VERIFIER", 0, SOL_MODE)
        self.assertEqual(select_reviewer(self.policy, "GEMINI_FLASH_HIGH", k0).selected_endpoint, "SOL_HIGH")
        self.assertEqual(select_reviewer(self.policy, "SOL_HIGH", k0).selected_endpoint, "GROK_4_6_HIGH")


if __name__ == "__main__":
    unittest.main()
