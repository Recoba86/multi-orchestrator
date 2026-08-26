"""Tests for pure deterministic weighted selector (Task 3).

Normative reference:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§6)
"""

import collections
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import (
    CandidateWeight,
    RuntimePolicy,
    load_runtime_policy,
    weights_for,
)
from core.runtime_weighted_selector import (
    ALGORITHM_VERSION,
    DOMAIN_SEPARATOR,
    NoEligibleCandidateError,
    SelectionEvidence,
    SelectionKey,
    select_candidate,
    weighted_select,
)

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class SelectionKeyTests(unittest.TestCase):
    def test_valid_key_construction_and_canonical_encoding(self):
        key = SelectionKey(
            mission_id="m1",
            role="SCOUT",
            ordinal=0,
            mode=SOL_MODE,
        )
        self.assertEqual(key.mission_id, "m1")
        self.assertEqual(key.role, "SCOUT")
        self.assertEqual(key.ordinal, 0)
        self.assertEqual(key.mode, SOL_MODE)

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
            with self.assertRaises(ValueError, msg=f"Should reject {bad!r}"):
                SelectionKey(mission_id=bad, role="SCOUT", ordinal=0, mode=SOL_MODE)  # type: ignore

    def test_invalid_role(self):
        for bad in ("", None, 123, {}):
            with self.assertRaises(ValueError, msg=f"Should reject {bad!r}"):
                SelectionKey(mission_id="m1", role=bad, ordinal=0, mode=SOL_MODE)  # type: ignore

    def test_invalid_ordinal(self):
        for bad in (-1, -10, 1.5, True, False, "0", None):
            with self.assertRaises(ValueError, msg=f"Should reject {bad!r}"):
                SelectionKey(mission_id="m1", role="SCOUT", ordinal=bad, mode=SOL_MODE)  # type: ignore

    def test_invalid_mode(self):
        for bad in ("SolMode", "SOL_MODE", "sol_mode", None, 1):
            with self.assertRaises(ValueError, msg=f"Should reject {bad!r}"):
                SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=bad)  # type: ignore


class PureWeightedSelectorTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)

    # -------------------------------------------------------------------------
    # 1. SAME INPUT DETERMINISM
    # -------------------------------------------------------------------------
    def test_same_input_determinism(self):
        candidates = (
            CandidateWeight("GEMINI_FLASH_HIGH", 70.0),
            CandidateWeight("PLUS_LUNA", 20.0),
            CandidateWeight("STEP_3_7_FLASH", 10.0),
        )
        key = SelectionKey(mission_id="mission-alpha", role="SCOUT", ordinal=3, mode=SOL_MODE)
        res1 = weighted_select(candidates, key)
        res2 = weighted_select(candidates, key)
        self.assertEqual(res1.selected_endpoint, res2.selected_endpoint)
        self.assertEqual(res1.bucket, res2.bucket)
        self.assertEqual(res1.total_weight_units, res2.total_weight_units)
        self.assertEqual(res1.selection_key_digest, res2.selection_key_digest)

    # -------------------------------------------------------------------------
    # 2. ORDINAL PARTICIPATION
    # -------------------------------------------------------------------------
    def test_ordinal_participation(self):
        candidates = (
            CandidateWeight("A", 50.0),
            CandidateWeight("B", 50.0),
        )
        results = [
            weighted_select(
                candidates,
                SelectionKey(mission_id="m1", role="WORKER", ordinal=i, mode=SOL_MODE),
            ).selected_endpoint
            for i in range(20)
        ]
        self.assertIn("A", results)
        self.assertIn("B", results)

    # -------------------------------------------------------------------------
    # 3. MISSION PARTICIPATION
    # -------------------------------------------------------------------------
    def test_mission_participation(self):
        candidates = (
            CandidateWeight("A", 50.0),
            CandidateWeight("B", 50.0),
        )
        digests = set()
        for i in range(10):
            key = SelectionKey(mission_id=f"mission-{i}", role="WORKER", ordinal=0, mode=SOL_MODE)
            res = weighted_select(candidates, key)
            digests.add(res.selection_key_digest)
        self.assertEqual(len(digests), 10)

    # -------------------------------------------------------------------------
    # 4. MODE PARTICIPATION
    # -------------------------------------------------------------------------
    def test_mode_participation(self):
        candidates = (
            CandidateWeight("A", 50.0),
            CandidateWeight("B", 50.0),
        )
        k_sol = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        k_grok = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=GROK_MODE)
        res_sol = weighted_select(candidates, k_sol)
        res_grok = weighted_select(candidates, k_grok)
        self.assertNotEqual(res_sol.selection_key_digest, res_grok.selection_key_digest)

    # -------------------------------------------------------------------------
    # 5. ROLE PARTICIPATION
    # -------------------------------------------------------------------------
    def test_role_participation(self):
        candidates = (
            CandidateWeight("A", 50.0),
            CandidateWeight("B", 50.0),
        )
        k_scout = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=SOL_MODE)
        k_worker = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        res_scout = weighted_select(candidates, k_scout)
        res_worker = weighted_select(candidates, k_worker)
        self.assertNotEqual(res_scout.selection_key_digest, res_worker.selection_key_digest)

    # -------------------------------------------------------------------------
    # 6. CROSS-PROCESS STABILITY (PYTHONHASHSEED independence)
    # -------------------------------------------------------------------------
    def test_cross_process_stability(self):
        code = """
import sys
from pathlib import Path
REPO_ROOT = Path('.').resolve()
sys.path.insert(0, str(REPO_ROOT))
from core.runtime_routing_mode import SOL_MODE
from core.runtime_routing_policy import CandidateWeight
from core.runtime_weighted_selector import SelectionKey, weighted_select

candidates = (CandidateWeight("A", 70.0), CandidateWeight("B", 30.0))
key = SelectionKey("fixed-mission", "SCOUT", 42, SOL_MODE)
print(weighted_select(candidates, key).selected_endpoint)
"""
        outputs = set()
        for seed in ("0", "42", "random", "123456"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            out = subprocess.check_output(
                [sys.executable, "-c", code],
                env=env,
                text=True,
                cwd=REPO_ROOT,
            ).strip()
            outputs.add(out)
        self.assertEqual(len(outputs), 1)

    # -------------------------------------------------------------------------
    # 7. KNOWN HASH / SELECTION VECTOR
    # -------------------------------------------------------------------------
    def test_known_selection_vector(self):
        key = SelectionKey(mission_id="canonical-test-mission", role="SCOUT", ordinal=0, mode=SOL_MODE)
        candidates = (
            CandidateWeight("ALPHA", 50.0),
            CandidateWeight("BETA", 50.0),
        )
        res = weighted_select(candidates, key)
        # Expected SHA-256 for canonical key encoding:
        key_bytes = key.canonical_bytes()
        expected_digest = hashlib.sha256(key_bytes).hexdigest()
        self.assertEqual(res.selection_key_digest, expected_digest)
        # Canonical order: ALPHA (500 units), BETA (500 units). Total = 1000 units.
        raw_int = int.from_bytes(hashlib.sha256(key_bytes).digest()[:8], "big")
        u = raw_int / (2**64)
        threshold = u * 1000.0
        expected_winner = "ALPHA" if threshold < 500.0 else "BETA"
        self.assertEqual(res.selected_endpoint, expected_winner)

    # -------------------------------------------------------------------------
    # 9. ORDER INDEPENDENCE
    # -------------------------------------------------------------------------
    def test_candidate_order_independence(self):
        key = SelectionKey(mission_id="order-test", role="WORKER", ordinal=7, mode=SOL_MODE)
        list1 = (
            CandidateWeight("C", 20.0),
            CandidateWeight("A", 50.0),
            CandidateWeight("B", 30.0),
        )
        list2 = (
            CandidateWeight("A", 50.0),
            CandidateWeight("B", 30.0),
            CandidateWeight("C", 20.0),
        )
        list3 = (
            CandidateWeight("B", 30.0),
            CandidateWeight("C", 20.0),
            CandidateWeight("A", 50.0),
        )
        res1 = weighted_select(list1, key)
        res2 = weighted_select(list2, key)
        res3 = weighted_select(list3, key)
        self.assertEqual(res1.selected_endpoint, res2.selected_endpoint)
        self.assertEqual(res2.selected_endpoint, res3.selected_endpoint)

    # -------------------------------------------------------------------------
    # 10. EXACT HALF-PERCENT REPRESENTATION (87.5 / 12.5)
    # -------------------------------------------------------------------------
    def test_exact_half_percent_representation(self):
        key = SelectionKey(mission_id="m1", role="SCOUT", ordinal=0, mode=GROK_MODE)
        candidates = (
            CandidateWeight("GEMINI_FLASH_HIGH", 87.5),
            CandidateWeight("STEP_3_7_FLASH", 12.5),
        )
        res = weighted_select(candidates, key)
        # 87.5 and 12.5 scaled by 10 -> 875 and 125 units, sum = 1000 units
        self.assertEqual(res.total_weight_units, 1000)
        self.assertIn(res.selected_endpoint, ("GEMINI_FLASH_HIGH", "STEP_3_7_FLASH"))

    # -------------------------------------------------------------------------
    # 11. DISTRIBUTION — SCOUT (70 / 20 / 10)
    # -------------------------------------------------------------------------
    def test_distribution_scout_70_20_10(self):
        candidates = (
            CandidateWeight("GEMINI_FLASH_HIGH", 70.0),
            CandidateWeight("PLUS_LUNA", 20.0),
            CandidateWeight("STEP_3_7_FLASH", 10.0),
        )
        counts = collections.Counter()
        n = 10000
        for i in range(n):
            key = SelectionKey(mission_id="dist-scout", role="SCOUT", ordinal=i, mode=SOL_MODE)
            res = weighted_select(candidates, key)
            counts[res.selected_endpoint] += 1

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.70, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.20, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.10, delta=0.02)

    # -------------------------------------------------------------------------
    # 12. DISTRIBUTION — WORKER (50 / 35 / 15)
    # -------------------------------------------------------------------------
    def test_distribution_worker_50_35_15(self):
        candidates = (
            CandidateWeight("GEMINI_FLASH_HIGH", 50.0),
            CandidateWeight("PLUS_LUNA", 35.0),
            CandidateWeight("STEP_3_7_FLASH", 15.0),
        )
        counts = collections.Counter()
        n = 10000
        for i in range(n):
            key = SelectionKey(mission_id="dist-worker", role="STANDARD_WORKER", ordinal=i, mode=SOL_MODE)
            res = weighted_select(candidates, key)
            counts[res.selected_endpoint] += 1

        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.50, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.35, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.15, delta=0.02)

    # -------------------------------------------------------------------------
    # 13. DISTRIBUTION — OX TABLE (30 / 35 / 25 / 10)
    # -------------------------------------------------------------------------
    def test_distribution_ox_table_30_35_25_10(self):
        candidates = (
            CandidateWeight("OX_ALPHA", 30.0),
            CandidateWeight("GEMINI_FLASH_HIGH", 35.0),
            CandidateWeight("PLUS_LUNA", 25.0),
            CandidateWeight("STEP_3_7_FLASH", 10.0),
        )
        counts = collections.Counter()
        n = 10000
        for i in range(n):
            key = SelectionKey(mission_id="dist-ox", role="STANDARD_WORKER", ordinal=i, mode=SOL_MODE)
            res = weighted_select(candidates, key)
            counts[res.selected_endpoint] += 1

        self.assertAlmostEqual(counts["OX_ALPHA"] / n, 0.30, delta=0.02)
        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 0.35, delta=0.02)
        self.assertAlmostEqual(counts["PLUS_LUNA"] / n, 0.25, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 0.10, delta=0.02)

    # -------------------------------------------------------------------------
    # 14. FILTERED RENORMALIZATION (60 : 25 : 10(unverified) : 5 -> 60:25:5 / 90)
    # -------------------------------------------------------------------------
    def test_filtered_renormalization_60_25_5(self):
        candidates = (
            CandidateWeight("GROK_4_6_HIGH", 60.0),
            CandidateWeight("GEMINI_FLASH_HIGH", 25.0),
            CandidateWeight("PLUS_LUNA_XHIGH", 10.0),
            CandidateWeight("STEP_3_7_FLASH", 5.0),
        )
        counts = collections.Counter()
        n = 10000
        for i in range(n):
            key = SelectionKey(mission_id="dist-deep", role="DEEP_WORKER", ordinal=i, mode=SOL_MODE)
            res = weighted_select(candidates, key, exclude={"PLUS_LUNA_XHIGH"})
            counts[res.selected_endpoint] += 1

        self.assertEqual(counts["PLUS_LUNA_XHIGH"], 0)
        # Expected relative ratios over 90 total:
        # GROK: 60/90 = 0.6667
        # GEMINI: 25/90 = 0.2778
        # STEP: 5/90 = 0.0556
        self.assertAlmostEqual(counts["GROK_4_6_HIGH"] / n, 60.0 / 90.0, delta=0.02)
        self.assertAlmostEqual(counts["GEMINI_FLASH_HIGH"] / n, 25.0 / 90.0, delta=0.02)
        self.assertAlmostEqual(counts["STEP_3_7_FLASH"] / n, 5.0 / 90.0, delta=0.02)

    # -------------------------------------------------------------------------
    # 15 & 16. POLICY-DRIVEN UNVERIFIED FILTER & NO SILENT LUNA SUBSTITUTION
    # -------------------------------------------------------------------------
    def test_select_candidate_with_policy_filters_unverified(self):
        deep_table = weights_for(self.policy, "DEEP_WORKER", SOL_MODE, False)
        key = SelectionKey(mission_id="policy-filter-test", role="DEEP_WORKER", ordinal=0, mode=SOL_MODE)
        res = select_candidate(self.policy, deep_table, key)
        self.assertNotIn("PLUS_LUNA_XHIGH", res.effective_candidates)
        self.assertIn("PLUS_LUNA_XHIGH", res.excluded_candidates)
        self.assertNotEqual(res.selected_endpoint, "PLUS_LUNA_XHIGH")
        # Ensure PLUS_LUNA is NOT selected (not in Deep Worker table)
        self.assertNotEqual(res.selected_endpoint, "PLUS_LUNA")

    # -------------------------------------------------------------------------
    # 17 & 18. EXPLICIT AND MULTIPLE EXCLUSIONS
    # -------------------------------------------------------------------------
    def test_explicit_and_multiple_exclusions(self):
        candidates = (
            CandidateWeight("A", 40.0),
            CandidateWeight("B", 30.0),
            CandidateWeight("C", 30.0),
        )
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        res = weighted_select(candidates, key, exclude={"A", "C"})
        self.assertEqual(res.selected_endpoint, "B")
        self.assertEqual(res.effective_candidates, ("B",))
        self.assertEqual(set(res.excluded_candidates), {"A", "C"})

    # -------------------------------------------------------------------------
    # 19. FAIL-CLOSED ON EMPTY SET AFTER FILTERING
    # -------------------------------------------------------------------------
    def test_fail_closed_empty_candidates(self):
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        with self.assertRaises(NoEligibleCandidateError):
            weighted_select((), key)

        candidates = (CandidateWeight("A", 100.0),)
        with self.assertRaises(NoEligibleCandidateError):
            weighted_select(candidates, key, exclude={"A"})

    # -------------------------------------------------------------------------
    # 20. SINGLE ELIGIBLE CANDIDATE
    # -------------------------------------------------------------------------
    def test_single_candidate(self):
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        candidates = (CandidateWeight("ONLY_ONE", 100.0),)
        res = weighted_select(candidates, key)
        self.assertEqual(res.selected_endpoint, "ONLY_ONE")
        self.assertEqual(res.effective_candidates, ("ONLY_ONE",))

    # -------------------------------------------------------------------------
    # 25. DUPLICATE ENDPOINT DEFENSE
    # -------------------------------------------------------------------------
    def test_duplicate_candidate_rejected(self):
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        candidates = (
            CandidateWeight("DUP", 50.0),
            CandidateWeight("DUP", 50.0),
        )
        with self.assertRaises(ValueError):
            weighted_select(candidates, key)

    # -------------------------------------------------------------------------
    # 26. INVALID WEIGHTS DEFENSE
    # -------------------------------------------------------------------------
    def test_invalid_weights_defenses(self):
        key = SelectionKey(mission_id="m1", role="WORKER", ordinal=0, mode=SOL_MODE)
        for bad_w in (-10.0, float("nan"), float("inf"), True, False):
            with self.assertRaises(ValueError):
                weighted_select((CandidateWeight("A", bad_w),), key)

    # -------------------------------------------------------------------------
    # 27 & 28. NO POLICY MUTATION AND NO SIDE EFFECTS
    # -------------------------------------------------------------------------
    def test_no_policy_mutation(self):
        deep_table = weights_for(self.policy, "DEEP_WORKER", SOL_MODE, False)
        orig_weights = [(c.endpoint_id, c.weight) for c in deep_table]
        key = SelectionKey(mission_id="m1", role="DEEP_WORKER", ordinal=0, mode=SOL_MODE)
        select_candidate(self.policy, deep_table, key)
        post_weights = [(c.endpoint_id, c.weight) for c in deep_table]
        self.assertEqual(orig_weights, post_weights)

    # -------------------------------------------------------------------------
    # 30. BOSS PRIORITY CHAIN NOT ACCEPTED AS WEIGHTED TABLE
    # -------------------------------------------------------------------------
    def test_boss_chain_not_accepted(self):
        key = SelectionKey(mission_id="m1", role="BOSS", ordinal=0, mode=SOL_MODE)
        boss_chain = ("SOL_HIGH", "GROK_4_6_HIGH")
        with self.assertRaises(TypeError):
            weighted_select(boss_chain, key)  # type: ignore


if __name__ == "__main__":
    unittest.main()
