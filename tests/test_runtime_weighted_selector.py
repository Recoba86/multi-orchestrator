"""Primary-first selector tests. Digest is audit-only."""

import ast
import inspect
import json
import os
from pathlib import Path
import subprocess
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

    def test_bucket_is_exact_integer(self):
        cands = (CandidateWeight("A", 70.0), CandidateWeight("B", 30.0))
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE)
        res = weighted_select(cands, key)
        self.assertIsInstance(res.bucket, int)
        self.assertNotIsInstance(res.bucket, bool)

    def test_no_float_division_in_selector_decision(self):
        source = inspect.getsource(weighted_select)
        tree = ast.parse(source)
        self.assertFalse(
            any(isinstance(node, ast.Div) for node in ast.walk(tree)),
            "weighted_select must not use floating-point division",
        )

    def test_same_input_determinism(self):
        cands = (
            CandidateWeight("GEMINI_FLASH_HIGH", 70.0),
            CandidateWeight("PLUS_LUNA", 20.0),
            CandidateWeight("STEP_3_7_FLASH", 10.0),
        )
        key = SelectionKey(mission_id="mission-alpha", role="SCOUT", ordinal=3, mode=SOL_MODE)
        first = weighted_select(cands, key)
        second = weighted_select(cands, key)
        self.assertEqual(first, second)

    def test_mission_participation(self):
        cands = (CandidateWeight("A", 50.0), CandidateWeight("B", 50.0))
        digests = {
            weighted_select(
                cands,
                SelectionKey(mission_id=f"mission-{i}", role="WORKER", ordinal=0, mode=SOL_MODE),
            ).selection_key_digest
            for i in range(10)
        }
        self.assertEqual(len(digests), 10)

    def test_mode_participation(self):
        cands = (CandidateWeight("A", 50.0), CandidateWeight("B", 50.0))
        sol = weighted_select(
            cands,
            SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE),
        )
        from core.runtime_routing_mode import GROK_MODE
        grok = weighted_select(
            cands,
            SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=GROK_MODE),
        )
        self.assertNotEqual(sol.selection_key_digest, grok.selection_key_digest)

    def test_role_participation(self):
        cands = (CandidateWeight("A", 50.0), CandidateWeight("B", 50.0))
        scout = weighted_select(
            cands,
            SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE),
        )
        worker = weighted_select(
            cands,
            SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE),
        )
        self.assertNotEqual(scout.selection_key_digest, worker.selection_key_digest)

    def test_cross_process_stability(self):
        code = """
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
from core.runtime_routing_mode import SOL_MODE
from core.runtime_routing_policy import CandidateWeight
from core.runtime_weighted_selector import SelectionKey, weighted_select
res = weighted_select(
    (CandidateWeight("A", 70.0), CandidateWeight("B", 30.0)),
    SelectionKey("fixed-mission", "SCOUT", 42, SOL_MODE),
)
print(f"{res.selected_endpoint}:{res.bucket}:{res.selection_key_digest}")
"""
        outputs = set()
        for seed in ("0", "42", "random", "123456"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outputs.add(
                subprocess.check_output(
                    [sys.executable, "-c", code],
                    env=env,
                    text=True,
                    cwd=REPO_ROOT,
                ).strip()
            )
        self.assertEqual(len(outputs), 1)

    def test_exact_half_percent_representation(self):
        from core.runtime_routing_mode import GROK_MODE
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=GROK_MODE)
        res = weighted_select(
            (CandidateWeight("A", 87.5), CandidateWeight("B", 12.5)),
            key,
        )
        self.assertEqual(res.total_weight_units, 1000)
        self.assertEqual(res.selected_endpoint, "A")
        self.assertIsInstance(res.bucket, int)

    def test_explicit_and_multiple_exclusions(self):
        cands = (
            CandidateWeight("A", 40.0),
            CandidateWeight("B", 30.0),
            CandidateWeight("C", 30.0),
        )
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        res = weighted_select(cands, key, exclude={"A", "C"})
        self.assertEqual(res.selected_endpoint, "B")
        self.assertEqual(res.effective_candidates, ("B",))
        self.assertEqual(set(res.excluded_candidates), {"A", "C"})

    def test_fail_closed_empty_candidates(self):
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        with self.assertRaises(NoEligibleCandidateError):
            weighted_select((), key)
        with self.assertRaises(NoEligibleCandidateError):
            weighted_select((CandidateWeight("A", 100.0),), key, exclude={"A"})

    def test_single_candidate(self):
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        res = weighted_select((CandidateWeight("ONLY_ONE", 100.0),), key)
        self.assertEqual(res.selected_endpoint, "ONLY_ONE")
        self.assertEqual(res.effective_candidates, ("ONLY_ONE",))

    def test_invalid_weights_defenses(self):
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        for bad_weight in (-10.0, float("nan"), float("inf"), True, False):
            with self.assertRaises(ValueError):
                weighted_select((CandidateWeight("A", bad_weight),), key)

    def test_no_policy_mutation(self):
        cands = weights_for(self.policy, "DEEP_WORKER", SOL_MODE, False)
        before = tuple((c.endpoint_id, c.weight) for c in cands)
        key = SelectionKey(mission_id="m1", role="DEEP_WORKER", ordinal=0, mode=SOL_MODE)
        select_candidate(self.policy, cands, key)
        self.assertEqual(before, tuple((c.endpoint_id, c.weight) for c in cands))

    def test_boss_chain_not_accepted(self):
        key = SelectionKey(mission_id="m1", role="BOSS", ordinal=0, mode=SOL_MODE)
        with self.assertRaises(TypeError):
            weighted_select(("SOL_HIGH", "GROK_4_6_HIGH"), key)


if __name__ == "__main__":
    unittest.main()
