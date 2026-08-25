#!/usr/bin/env python3
"""Focused tests for the read-only, deterministic model resolver."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core import model_intelligence as mi  # noqa: E402
from core.model_availability import (  # noqa: E402
    ErrorCategory,
    Freshness,
    ModelAvailabilityRecord,
    ModelStatus,
    PROVENANCE_PROBE,
)
from core.model_discovery import DiscoveryResult  # noqa: E402
from core.model_resolver import (  # noqa: E402
    ResolutionEvidence,
    RoleResolution,
    resolve_role,
)


UTC = timezone.utc
AS_OF = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def role_configuration(
    preferred: tuple[str, ...],
    fallback: tuple[str, ...] = (),
    hints: tuple[str, ...] = ("reasoning", "analysis"),
) -> dict:
    return {
        "planner": {
            "requires": ["decision-plane planning"],
            "preferred": list(preferred),
            "fallback": list(fallback),
            "capability_hints": list(hints),
        },
    }


def discovered(*models: str) -> tuple[DiscoveryResult, ...]:
    return (DiscoveryResult("codex-profiles", True, models, f"{len(models)} model(s)"),)


def available(model: str, *, latency_ms: float = 10.0) -> ModelAvailabilityRecord:
    return ModelAvailabilityRecord(
        model_id=model,
        provider_id="test-provider",
        status=ModelStatus.AVAILABLE,
        provenance=PROVENANCE_PROBE,
        freshness=Freshness.FRESH,
        checked_at=AS_OF,
        latency_ms=latency_ms,
    )


def unavailable(model: str) -> ModelAvailabilityRecord:
    return ModelAvailabilityRecord(
        model_id=model,
        provider_id="test-provider",
        status=ModelStatus.UNAVAILABLE,
        provenance=PROVENANCE_PROBE,
        freshness=Freshness.FRESH,
        checked_at=AS_OF,
        latency_ms=5.0,
        error_category=ErrorCategory.SERVER,
    )


def evidence(evidence_id: str, strength: str = "HIGH") -> mi.EvidenceRecord:
    return mi.EvidenceRecord(
        id=evidence_id,
        source_type="fixture",
        strength=strength,
        locator=f"urn:fixture:{evidence_id}",
        observed_at=AS_OF - timedelta(hours=1),
        summary=f"{evidence_id} fixture",
    )


def active_profile(
    model: str,
    *,
    reasoning_score: int = 8,
    reasoning_confidence: str = "HIGH",
    analysis_score: int = 7,
) -> mi.ModelProfile:
    return mi.build_profile(
        model,
        {
            "reasoning": mi.CapabilityClaim(
                "reasoning",
                reasoning_score,
                reasoning_confidence,
                evidence=(evidence(f"{model}-reasoning"),),
            ),
            "analysis": mi.CapabilityClaim(
                "analysis",
                analysis_score,
                "MEDIUM",
                evidence=(evidence(f"{model}-analysis", "MEDIUM"),),
            ),
        },
        as_of=AS_OF,
    )


class ModelResolverTests(unittest.TestCase):
    def test_offline_default_never_recommends_unknown_availability(self):
        configuration = role_configuration(("gpt-5.6-sol",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("gpt-5.6-sol"),
        )

        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].outcome, "UNRESOLVED")
        self.assertEqual(result.candidates[0].reason, "availability-unknown")
        self.assertEqual(result.candidates[0].evidence.status, "UNKNOWN")
        self.assertEqual(result.candidates[0].evidence.freshness, "UNKNOWN")
        self.assertIsNone(result.candidates[0].evidence.checked_at)
        self.assertIsNone(result.candidates[0].evidence.latency_ms)
        self.assertIsNone(result.candidates[0].evidence.confidence)
        self.assertEqual(result.recommendations, ())
        self.assertEqual(result.outcome, "UNRESOLVED")
        self.assertIsNone(result.resolved_model)

    def test_identity_matching_is_exact_without_alias_or_fuzzy(self):
        configuration = role_configuration(("gpt-5.6-sol",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("GPT-5.6-SOL"),
            availability={"gpt-5.6-sol": available("gpt-5.6-sol")},
        )

        self.assertEqual(result.candidates[0].outcome, "REJECTED")
        self.assertEqual(result.candidates[0].reason, "not-discovered")

    def test_not_discovered_is_rejected_even_when_available(self):
        configuration = role_configuration(("gpt-5.6-sol",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=(),
            availability={"gpt-5.6-sol": available("gpt-5.6-sol")},
        )

        self.assertEqual(result.candidates[0].outcome, "REJECTED")
        self.assertEqual(result.candidates[0].reason, "not-discovered")

    def test_explicitly_unavailable_is_rejected(self):
        configuration = role_configuration(("gpt-5.6-sol",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("gpt-5.6-sol"),
            availability={"gpt-5.6-sol": unavailable("gpt-5.6-sol")},
        )

        self.assertEqual(result.candidates[0].outcome, "REJECTED")
        self.assertEqual(result.candidates[0].reason, "unavailable")
        self.assertEqual(result.candidates[0].evidence.status, "UNAVAILABLE")

    def test_available_compatible_active_profile_is_recommended(self):
        configuration = role_configuration(("gpt-5.6-sol",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("gpt-5.6-sol"),
            availability={"gpt-5.6-sol": available("gpt-5.6-sol")},
            profiles=[active_profile("gpt-5.6-sol")],
        )

        self.assertEqual(result.candidates[0].outcome, "RECOMMENDED")
        self.assertEqual(result.candidates[0].reason, "recommended")
        self.assertEqual(result.recommendations, (result.candidates[0],))
        self.assertEqual(result.outcome, "RECOMMENDED")
        self.assertEqual(result.resolved_model, "gpt-5.6-sol")
        self.assertAlmostEqual(result.candidates[0].coverage, 0.65)

    def test_available_but_unknown_metadata_is_unresolved(self):
        configuration = role_configuration(("provider/not-in-catalog",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("provider/not-in-catalog"),
            availability={"provider/not-in-catalog": available("provider/not-in-catalog")},
        )

        self.assertEqual(result.candidates[0].outcome, "UNRESOLVED")
        self.assertEqual(result.candidates[0].reason, "metadata-unavailable")

    def test_available_but_incompatible_capabilities_is_unresolved(self):
        configuration = role_configuration(
            ("opencode-go/deepseek-v4-flash",), hints=("review",)
        )
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("opencode-go/deepseek-v4-flash"),
            availability={
                "opencode-go/deepseek-v4-flash": available("opencode-go/deepseek-v4-flash")
            },
        )

        self.assertEqual(result.candidates[0].outcome, "UNRESOLVED")
        self.assertEqual(result.candidates[0].reason, "capability-incompatible")

    def test_available_compatible_without_profile_is_unresolved(self):
        configuration = role_configuration(("gpt-5.6-sol",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("gpt-5.6-sol"),
            availability={"gpt-5.6-sol": available("gpt-5.6-sol")},
        )

        self.assertEqual(result.candidates[0].outcome, "UNRESOLVED")
        self.assertEqual(result.candidates[0].reason, "insufficient-intelligence-evidence")

    def test_recommendations_follow_deterministic_tie_break(self):
        configuration = role_configuration(("gpt-5.6-sol", "gpt-5.6-luna"))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("gpt-5.6-sol", "gpt-5.6-luna"),
            availability={
                "gpt-5.6-sol": available("gpt-5.6-sol"),
                "gpt-5.6-luna": available("gpt-5.6-luna"),
            },
            profiles=[
                active_profile("gpt-5.6-luna", reasoning_score=6, analysis_score=5),
                active_profile("gpt-5.6-sol", reasoning_score=8, analysis_score=7),
            ],
        )

        self.assertEqual(
            [item.raw_identity for item in result.recommendations],
            ["gpt-5.6-sol", "gpt-5.6-luna"],
        )

    def test_evidence_dimensions_are_separate(self):
        configuration = role_configuration(("gpt-5.6-sol",))
        result = resolve_role(
            configuration,
            "planner",
            discovery=discovered("gpt-5.6-sol"),
            availability={"gpt-5.6-sol": available("gpt-5.6-sol", latency_ms=42.5)},
            profiles=[active_profile("gpt-5.6-sol")],
        )

        evidence = result.candidates[0].evidence
        self.assertIsInstance(evidence, ResolutionEvidence)
        self.assertEqual(evidence.status, "AVAILABLE")
        self.assertEqual(evidence.freshness, "FRESH")
        self.assertEqual(evidence.provenance, PROVENANCE_PROBE)
        self.assertEqual(evidence.checked_at, AS_OF)
        self.assertEqual(evidence.latency_ms, 42.5)
        self.assertIsNotNone(evidence.confidence)

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_role(role_configuration(("gpt-5.6-sol",)), "boss")

    def test_no_configured_candidates_returns_unknown(self):
        result = resolve_role({"planner": {"preferred": []}}, "planner")
        self.assertIsInstance(result, RoleResolution)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.recommendations, ())
        self.assertEqual(result.outcome, "UNKNOWN")
        self.assertIsNone(result.resolved_model)


if __name__ == "__main__":
    unittest.main()
