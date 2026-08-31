"""Primary-first selector tests. Digest is audit-only."""

import json
from pathlib import Path
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_routing_mode import SOL_MODE
from core.runtime_routing_policy import CandidateWeight, load_runtime_policy, weights_for
from core.runtime_weighted_selector import (
    ALGORITHM_VERSION,
    DOMAIN_SEPARATOR,
    NoEligibleCandidateError,
    SelectionKey,
    select_candidate,
    weighted_select,
)

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class SelectionKeyTests(unittest.TestCase):
    def test_valid_key_construction_and_canonical_encoding(self):
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE)
        expected_payload = {
            "version": ALGORITHM_VERSION,
            "domain": DOMAIN_SEPARATOR,
            "mode": "SolMode",
            "mission_id": "m1",
            "role": "SCOUT",
            "ordinal": 0,
        }
        expected_bytes = json.dumps(expected_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.assertEqual(key.canonical_bytes(), expected_bytes)

    def test_invalid_mission_id(self):
        for bad in ("", None, 123, []):
            with self.assertRaises((ValueError, TypeError)):
                SelectionKey(mission_id=bad, role="SCOUT", ordinal=0, mode=SOL_MODE)  # type: ignore

    def test_invalid_role(self):
        for bad in ("", None, 123, {}):
            with self.assertRaises((ValueError, TypeError)):
                SelectionKey(mission_id="m1", role=bad, ordinal=0, mode=SOL_MODE)  # type: ignore

    def test_invalid_ordinal(self):
        for bad in (-1, -10, 1.5, True, False, "0", None):
            with self.assertRaises((ValueError, TypeError)):
                SelectionKey(mission_id="m1", role="SCOUT", ordinal=bad, mode=SOL_MODE)  # type: ignore

    def test_invalid_mode(self):
        for bad in ("SolMode", "SOL_MODE", "sol_mode", None, 1):
            with self.assertRaises((ValueError, TypeError)):
                SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=bad)  # type: ignore


class PrimaryFirstSelectorTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)

    def test_declared_order_selects_first_survivor(self):
        cands = (CandidateWeight("A", 1.0), CandidateWeight("B", 99.0), CandidateWeight("C", 0.0))
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE)
        self.assertEqual(weighted_select(cands, key).selected_endpoint, "A")

    def test_ordinal_does_not_skip_healthy_primary(self):
        cands = weights_for(self.policy, "SCOUT", SOL_MODE, False)
        endpoints = set()
        for i in range(30):
            key = SelectionKey(mission_id="m-ord", role="SCOUT", ordinal=i, mode=SOL_MODE)
            endpoints.add(weighted_select(cands, key).selected_endpoint)
        self.assertEqual(endpoints, {"GEMINI_FLASH_MEDIUM"})

    def test_exclude_primary_advances_to_next(self):
        cands = (CandidateWeight("A", 100.0), CandidateWeight("B", 0.0))
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE)
        res = weighted_select(cands, key, exclude={"A"})
        self.assertEqual(res.selected_endpoint, "B")
        self.assertEqual(res.excluded_candidates, ("A",))

    def test_all_excluded_fails_closed(self):
        cands = (CandidateWeight("A", 100.0), CandidateWeight("B", 0.0))
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE)
        with self.assertRaises(NoEligibleCandidateError):
            weighted_select(cands, key, exclude={"A", "B"})

    def test_duplicate_candidate_rejected(self):
        cands = (CandidateWeight("A", 50.0), CandidateWeight("A", 50.0))
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE)
        with self.assertRaises(ValueError):
            weighted_select(cands, key)

    def test_select_candidate_filters_unverified(self):
        cands = weights_for(self.policy, "DEEP_WORKER", SOL_MODE, False)
        key = SelectionKey(mission_id="m1", role="DEEP_WORKER", ordinal=0, mode=SOL_MODE)
        res = select_candidate(self.policy, cands, key)
        self.assertEqual(res.selected_endpoint, "GROK_4_6_HIGH")
        self.assertNotIn("PLUS_LUNA_XHIGH", res.effective_candidates)


if __name__ == "__main__":
    unittest.main()
