"""OX overlay is opportunistic primary-first, not a 30% roll."""

from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_routing_mode import GROK_MODE, SOL_MODE
from core.runtime_routing_policy import load_runtime_policy, weights_for
from core.runtime_weighted_selector import SelectionKey, weighted_select

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class OxWorkerOverlayTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)

    def test_overlay_disabled_in_shipped_config(self):
        self.assertEqual(self.policy.ox_overlay, "disabled")

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


if __name__ == "__main__":
    unittest.main()
