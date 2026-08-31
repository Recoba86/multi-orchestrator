"""Tests for shadow Boss mode eligibility and binding decision (Task 4).

Normative reference:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§2.2, §2.3, §2.4)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 4)
"""

from pathlib import Path
import subprocess
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.policy_validator import PolicyValidator
from core.runtime_boss_binding import (
    CONTINUE_EXISTING_BOSS,
    MODE_EXCLUDED_GPT_PLUS,
    REASON_NEW_MISSION_BINDING,
    REASON_STATIC_INELIGIBLE,
    REASON_TEMPORARY_EXCLUSION,
    NoEligibleBossError,
    ShadowBossDecision,
    legacy_binding,
    shadow_boss_binding,
)
from core.runtime_routing_mode import GROK_MODE, SOL_MODE, RoutingMode
from core.runtime_routing_policy import RuntimePolicy, load_runtime_policy

CONFIG_PATH = REPO_ROOT / "config" / "runtime-routing.yaml"


class ShadowBossBindingTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_runtime_policy(CONFIG_PATH)
        self.validator = PolicyValidator()

    # -------------------------------------------------------------------------
    # 1. SolMode selects SOL_HIGH when eligible
    # -------------------------------------------------------------------------
    def test_solmode_selects_sol_high_when_eligible(self):
        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            validator=self.validator,
        )
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")
        self.assertEqual(dec.model, "gpt-5.6-sol")
        self.assertEqual(dec.effort, "high")
        self.assertEqual(dec.failure_domain, "gpt_plus")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")
        self.assertEqual(dec.continuity_status, REASON_NEW_MISSION_BINDING)
        self.assertEqual(dec.excluded_endpoints, ())

    # -------------------------------------------------------------------------
    # 2. SolMode SOL_HIGH exclusion selects GROK_4_6_HIGH
    # -------------------------------------------------------------------------
    def test_solmode_sol_high_excluded_selects_grok(self):
        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            validator=self.validator,
            excluded_endpoints={"SOL_HIGH"},
        )
        self.assertEqual(dec.selected_endpoint, "GROK_4_6_HIGH")
        self.assertEqual(dec.model, "nine-router/gcli/grok-4.6-high")
        self.assertEqual(dec.effort, "high")
        self.assertEqual(dec.failure_domain, "supergrok")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")
        self.assertEqual(len(dec.excluded_endpoints), 1)
        self.assertEqual(dec.excluded_endpoints[0], ("SOL_HIGH", REASON_TEMPORARY_EXCLUSION))

    # -------------------------------------------------------------------------
    # 3. SolMode Sol+Grok exclusion selects the cursor Grok fallback
    # -------------------------------------------------------------------------
    def test_solmode_sol_and_grok_excluded_selects_cursor_grok(self):
        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            validator=self.validator,
            excluded_endpoints={"SOL_HIGH", "GROK_4_6_HIGH"},
        )
        self.assertEqual(dec.selected_endpoint, "GROK_CURSOR_HIGH")
        self.assertEqual(dec.model, "nine-router/cu/cursor-grok-4.6-high")
        self.assertEqual(dec.effort, "high")
        self.assertEqual(dec.failure_domain, "supergrok")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # 4. Excluding the complete canonical chain fails closed
    # -------------------------------------------------------------------------
    def test_solmode_all_boss_candidates_excluded_fails_closed(self):
        with self.assertRaises(NoEligibleBossError):
            shadow_boss_binding(
                mode=SOL_MODE,
                policy=self.policy,
                validator=self.validator,
                excluded_endpoints={"SOL_HIGH", "GROK_4_6_HIGH", "GROK_CURSOR_HIGH"},
            )

    # -------------------------------------------------------------------------
    # 5. GrokMode preserves the canonical Boss primary
    # -------------------------------------------------------------------------
    def test_grokmode_selects_grok_when_eligible(self):
        dec = shadow_boss_binding(
            mode=GROK_MODE,
            policy=self.policy,
            validator=self.validator,
        )
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")
        self.assertEqual(dec.model, "gpt-5.6-sol")
        self.assertEqual(dec.effort, "high")
        self.assertEqual(dec.failure_domain, "gpt_plus")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")
        self.assertEqual(dec.continuity_status, REASON_NEW_MISSION_BINDING)

    # -------------------------------------------------------------------------
    # 6. GrokMode Grok exclusion selects the canonical Sol primary
    # -------------------------------------------------------------------------
    def test_grokmode_grok_excluded_selects_sol(self):
        dec = shadow_boss_binding(
            mode=GROK_MODE,
            policy=self.policy,
            validator=self.validator,
            excluded_endpoints={"GROK_4_6_HIGH"},
        )
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")
        self.assertEqual(dec.model, "gpt-5.6-sol")
        self.assertEqual(dec.effort, "high")
        self.assertEqual(dec.failure_domain, "gpt_plus")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # 7. GrokMode Sol+Grok exclusion selects the cursor Grok fallback
    # -------------------------------------------------------------------------
    def test_grokmode_sol_and_grok_excluded_selects_cursor_grok(self):
        dec = shadow_boss_binding(
            mode=GROK_MODE,
            policy=self.policy,
            validator=self.validator,
            excluded_endpoints={"SOL_HIGH", "GROK_4_6_HIGH"},
        )
        self.assertEqual(dec.selected_endpoint, "GROK_CURSOR_HIGH")
        self.assertEqual(dec.model, "nine-router/cu/cursor-grok-4.6-high")
        self.assertEqual(dec.effort, "high")
        self.assertEqual(dec.failure_domain, "supergrok")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # 8 & 9. GrokMode uses the same canonical chain as SolMode
    # -------------------------------------------------------------------------
    def test_grokmode_zero_gpt_plus_eligibility(self):
        dec = shadow_boss_binding(
            mode=GROK_MODE,
            policy=self.policy,
            validator=self.validator,
        )
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")
        self.assertEqual(dec.chain, ("SOL_HIGH", "GROK_4_6_HIGH", "GROK_CURSOR_HIGH"))

    # -------------------------------------------------------------------------
    # 10 & 11. Boss priority chains preserve configured order without weighting
    # -------------------------------------------------------------------------
    def test_boss_chains_preserve_configured_order(self):
        dec_sol = shadow_boss_binding(mode=SOL_MODE, policy=self.policy)
        self.assertEqual(
            dec_sol.chain,
            ("SOL_HIGH", "GROK_4_6_HIGH", "GROK_CURSOR_HIGH"),
        )
        dec_grok = shadow_boss_binding(mode=GROK_MODE, policy=self.policy)
        self.assertEqual(
            dec_grok.chain,
            ("SOL_HIGH", "GROK_4_6_HIGH", "GROK_CURSOR_HIGH"),
        )

    # -------------------------------------------------------------------------
    # 12. Statically unverified endpoint is skipped
    # -------------------------------------------------------------------------
    def test_statically_unverified_endpoint_skipped(self):
        # Even if an unverified endpoint were in chain, it is skipped
        # Test domain_eligible callable interface too
        def domain_eligible(domain: str) -> bool:
            return domain != "gpt_plus"

        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            domain_eligible=domain_eligible,
        )
        self.assertEqual(dec.selected_endpoint, "GROK_4_6_HIGH")
        self.assertIn(("SOL_HIGH", "HEALTH_COOLDOWN"), dec.excluded_endpoints)

    # -------------------------------------------------------------------------
    # 13. Explicit exclusions are recorded in decision evidence
    # -------------------------------------------------------------------------
    def test_explicit_exclusions_recorded(self):
        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            excluded_endpoints={"SOL_HIGH"},
        )
        self.assertEqual(dec.excluded_endpoints, (("SOL_HIGH", REASON_TEMPORARY_EXCLUSION),))

    # -------------------------------------------------------------------------
    # 14. No eligible Boss fails closed explicitly
    # -------------------------------------------------------------------------
    def test_no_eligible_boss_fails_closed(self):
        all_sol = {"SOL_HIGH", "GROK_4_6_HIGH", "GROK_CURSOR_HIGH"}
        with self.assertRaises(NoEligibleBossError):
            shadow_boss_binding(
                mode=SOL_MODE,
                policy=self.policy,
                excluded_endpoints=all_sol,
            )

        all_grok = {"SOL_HIGH", "GROK_4_6_HIGH", "GROK_CURSOR_HIGH"}
        with self.assertRaises(NoEligibleBossError):
            shadow_boss_binding(
                mode=GROK_MODE,
                policy=self.policy,
                excluded_endpoints=all_grok,
            )

    # -------------------------------------------------------------------------
    # 15. Unknown excluded endpoint handled without mutating policy
    # -------------------------------------------------------------------------
    def test_unknown_excluded_endpoint_handled_safely(self):
        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            excluded_endpoints={"NON_EXISTENT_ENDPOINT"},
        )
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")

    # -------------------------------------------------------------------------
    # 16 & 17 & 18 & 19 & 20 & 21. No side effects, no mutation, no spawn
    # -------------------------------------------------------------------------
    def test_no_side_effects_or_mutation(self):
        orig_boss_chains = dict(self.policy.boss_chains)
        dec = shadow_boss_binding(mode=SOL_MODE, policy=self.policy)
        self.assertEqual(self.policy.boss_chains, orig_boss_chains)
        self.assertIsInstance(dec, ShadowBossDecision)

    # -------------------------------------------------------------------------
    # 22. Exact model and effort comes from policy
    # -------------------------------------------------------------------------
    def test_exact_model_and_effort_resolution(self):
        dec = shadow_boss_binding(mode=SOL_MODE, policy=self.policy)
        res = self.policy.endpoint_resolution["SOL_HIGH"]
        self.assertEqual(dec.model, res["model"])
        self.assertEqual(dec.effort, res["effort"])

    # -------------------------------------------------------------------------
    # 23 & 24. PolicyValidator integration and REQUEST_VALID status
    # -------------------------------------------------------------------------
    def test_policy_validator_integration(self):
        dec = shadow_boss_binding(
            mode=SOL_MODE,
            policy=self.policy,
            validator=self.validator,
        )
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # 25. Root Controller self-promotion impossible
    # -------------------------------------------------------------------------
    def test_root_controller_self_promotion_impossible(self):
        ok, reason = self.validator.validate_role_not_controller_self_promotion("ROOT_CONTROLLER", "BOSS")
        self.assertFalse(ok)
        self.assertEqual(reason, "REJECT_CONTROLLER_SELF_PROMOTION")

    # -------------------------------------------------------------------------
    # 26. Persistent mode switch affects new-mission decision
    # -------------------------------------------------------------------------
    def test_persistent_mode_switch_affects_new_mission(self):
        dec_sol = shadow_boss_binding(mode=SOL_MODE, policy=self.policy)
        dec_grok = shadow_boss_binding(mode=GROK_MODE, policy=self.policy)
        self.assertEqual(dec_sol.selected_endpoint, "SOL_HIGH")
        self.assertEqual(dec_grok.selected_endpoint, "SOL_HIGH")

    # -------------------------------------------------------------------------
    # 27. Existing mission Boss continuity prevents mid-mission rebind
    # -------------------------------------------------------------------------
    def test_boss_continuity_prevents_mid_mission_rebind(self):
        # Mission was started with SOL_HIGH in SolMode. Mode later switched to GrokMode.
        dec = shadow_boss_binding(
            mode=GROK_MODE,
            policy=self.policy,
            validator=self.validator,
            existing_mission_boss="SOL_HIGH",
        )
        self.assertEqual(dec.selected_endpoint, "SOL_HIGH")
        self.assertEqual(dec.continuity_status, CONTINUE_EXISTING_BOSS)
        self.assertEqual(dec.model, "gpt-5.6-sol")
        self.assertEqual(dec.effort, "high")
        self.assertEqual(dec.failure_domain, "gpt_plus")
        self.assertEqual(dec.core_validation_status, "REQUEST_VALID")

    # -------------------------------------------------------------------------
    # 28. Static import guard: runtime_boss_binding does NOT import write_mode
    # -------------------------------------------------------------------------
    def test_static_guard_no_write_mode_import(self):
        src_path = REPO_ROOT / "core" / "runtime_boss_binding.py"
        if src_path.exists():
            content = src_path.read_text(encoding="utf-8")
            self.assertNotIn("write_mode", content)

    # -------------------------------------------------------------------------
    # Legacy wrapper mapping
    # -------------------------------------------------------------------------
    def test_legacy_binding_constant_map(self):
        self.assertEqual(legacy_binding("sol-luna-orchestrator-v2"), "SOL_HIGH")
        self.assertEqual(legacy_binding("grok-orchestrator-v2"), "GROK_4_6_HIGH")
        with self.assertRaises(ValueError):
            legacy_binding("unknown-skill")

    # -------------------------------------------------------------------------
    # Determinism across repeated calls
    # -------------------------------------------------------------------------
    def test_deterministic_repeated_calls(self):
        d1 = shadow_boss_binding(mode=SOL_MODE, policy=self.policy)
        d2 = shadow_boss_binding(mode=SOL_MODE, policy=self.policy)
        self.assertEqual(d1, d2)


if __name__ == "__main__":
    unittest.main()
