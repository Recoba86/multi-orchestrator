"""Adaptive scheduler slot, ownership, and pipelined verifier tests."""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_adaptive_scheduler import AdaptiveScheduler, ScheduledTask, format_concurrency_table
from core.runtime_routing_policy import load_runtime_policy

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class AdaptiveSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.sched = AdaptiveScheduler(self.policy)

    def test_max_two_parallel_scouts(self):
        self.assertTrue(self.sched.dispatch(ScheduledTask("s1", "SCOUT")))
        self.assertTrue(self.sched.dispatch(ScheduledTask("s2", "SCOUT")))
        self.assertFalse(self.sched.dispatch(ScheduledTask("s3", "SCOUT")))

    def test_boss_not_counted(self):
        # Scheduler never accepts BOSS role into the 6-slot cap; callers keep Boss outside.
        self.assertEqual(self.sched.cfg.max_active_subagents, 6)

    def test_disjoint_owned_files_enforced(self):
        self.assertTrue(self.sched.dispatch(ScheduledTask("w1", "STANDARD_WORKER", owned_files=("a.py",))))
        self.assertFalse(self.sched.dispatch(ScheduledTask("w2", "STANDARD_WORKER", owned_files=("a.py",))))
        self.assertTrue(self.sched.dispatch(ScheduledTask("w3", "STANDARD_WORKER", owned_files=("b.py",))))

    def test_pipelined_verifier_waits_for_implementer(self):
        self.assertTrue(self.sched.dispatch(ScheduledTask("w1", "STANDARD_WORKER", owned_files=("a.py",))))
        self.assertFalse(
            self.sched.dispatch(ScheduledTask("v1", "VERIFIER", implementer_task_id="w1"))
        )
        self.sched.finish_task("w1", success=True)
        self.assertTrue(
            self.sched.dispatch(ScheduledTask("v1", "VERIFIER", implementer_task_id="w1"))
        )

    def test_concurrency_table_format(self):
        self.sched.dispatch(ScheduledTask("s1", "SCOUT"))
        text = format_concurrency_table(self.sched.snapshot())
        self.assertIn("Peak Active Subagents", text)
        self.assertIn("Scouts Spawned", text)


if __name__ == "__main__":
    unittest.main()
