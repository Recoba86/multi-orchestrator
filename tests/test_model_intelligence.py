#!/usr/bin/env python3
"""Focused offline tests for the model-intelligence core."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import inspect
from pathlib import Path
import tempfile
import unittest


from core import model_intelligence as mi


UTC = timezone.utc
AS_OF = datetime(2026, 8, 25, 12, tzinfo=UTC)


def evidence(
    evidence_id: str = "ev-fixture",
    *,
    strength: str = mi.EVIDENCE_STRENGTH_HIGH,
    observed_at: datetime = AS_OF - timedelta(hours=1),
    expires_at: datetime | None = None,
    locator: str = "urn:fixture:model-intelligence",
    summary: str = "fixture evidence",
) -> mi.EvidenceRecord:
    return mi.EvidenceRecord(
        id=evidence_id,
        source_type="fixture",
        strength=strength,
        locator=locator,
        observed_at=observed_at,
        expires_at=expires_at,
        summary=summary,
    )


def claim(
    capability: str,
    score: int = 8,
    confidence: str = mi.CONFIDENCE_HIGH,
    *,
    evidence_record: mi.EvidenceRecord | None = None,
) -> mi.CapabilityClaim:
    return mi.CapabilityClaim(
        capability=capability,
        score=score,
        confidence=confidence,
        evidence=(evidence_record or evidence()),
    )


def cache_payload(
    *,
    evidence_entries: list[dict[str, object]] | None = None,
    models: list[dict[str, object]] | None = None,
    schema_version: object = 1,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "evidence": evidence_entries
        if evidence_entries is not None
        else [
            {
                "id": "ev-cache",
                "source_type": "fixture",
                "strength": "HIGH",
                "locator": "urn:fixture:cache",
                "observed_at": "2026-08-25T11:00:00+00:00",
                "summary": "cache fixture",
            }
        ],
        "models": models
        if models is not None
        else [
            {
                "identity": "provider/model",
                "claims": [
                    {
                        "capability": "reasoning",
                        "score": 8,
                        "confidence": "HIGH",
                        "evidence_ids": ["ev-cache"],
                    }
                ],
            }
        ],
    }


class ModelIntelligenceTests(unittest.TestCase):
    def test_raw_identity_is_preserved_and_normalization_has_no_alias_table(self):
        identity = mi.ModelIdentity("  Provider/Model  ")

        self.assertEqual(identity.raw, "  Provider/Model  ")
        self.assertEqual(identity.normalized, "Provider/Model")
        self.assertEqual(mi.normalize_identity("Provider/Model"), "Provider/Model")
        self.assertNotEqual(identity.raw, identity.normalized)
        self.assertEqual(
            mi.normalize_identity("Provider/Model"),
            mi.normalize_identity(" Provider/Model "),
        )

    def test_evidence_has_stable_identity_strength_and_inert_locator(self):
        item = evidence()

        self.assertEqual(item.id, "ev-fixture")
        self.assertEqual(item.source_type, "fixture")
        self.assertEqual(item.strength, mi.EVIDENCE_STRENGTH_HIGH)
        self.assertEqual(item.summary, "fixture evidence")
        self.assertEqual(item.evidence_id, item.id)
        self.assertEqual(item.url, item.locator)
        self.assertEqual(item.provenance, item.source_type)
        with self.assertRaises(ValueError):
            evidence("")
        with self.assertRaises(ValueError):
            evidence(strength="UNKNOWN")
        with self.assertRaises(ValueError):
            evidence(locator="javascript:alert(1)")
        with self.assertRaises(ValueError):
            evidence(summary=" ")

    def test_scores_are_integer_and_confidence_categories_map_separately(self):
        for value in (True, False, 1.0, 8.5, -1, 11):
            with self.subTest(score=value):
                with self.assertRaises(ValueError):
                    claim("reasoning", score=value)  # type: ignore[arg-type]
        for value in (True, False, 0.5, "UNKNOWN"):
            with self.subTest(confidence=value):
                with self.assertRaises(ValueError):
                    claim("reasoning", confidence=value)  # type: ignore[arg-type]

        low = claim("reasoning", confidence=mi.CONFIDENCE_LOW)
        medium = claim("reasoning", confidence=mi.CONFIDENCE_MEDIUM)
        high = claim("reasoning", confidence=mi.CONFIDENCE_HIGH)
        self.assertEqual(low.confidence, "LOW")
        self.assertEqual(medium.confidence, "MEDIUM")
        self.assertEqual(high.confidence, "HIGH")
        self.assertEqual(
            (low.confidence_value, medium.confidence_value, high.confidence_value),
            (0.25, 0.5, 0.9),
        )
        self.assertEqual(evidence(strength="LOW").strength, "LOW")
        self.assertEqual(high.confidence_value, mi.CONFIDENCE_CATEGORY_VALUES["HIGH"])

    def test_profiles_are_structurally_immutable(self):
        profile = mi.build_profile(
            "provider/model", {"reasoning": claim("reasoning")}, as_of=AS_OF
        )

        self.assertEqual(profile.status, mi.STATUS_ACTIVE)
        with self.assertRaises(TypeError):
            profile.claims["coding"] = claim("coding")  # type: ignore[index]
        with self.assertRaises(dataclass_frozen_error()):
            profile.status = mi.STATUS_STALE  # type: ignore[misc]

    def test_freshness_is_deterministic_and_conflicts_withhold_claims(self):
        stale = mi.build_profile(
            "stale/model",
            {
                "reasoning": claim(
                    "reasoning",
                    evidence_record=evidence(
                        "ev-stale", expires_at=AS_OF - timedelta(seconds=1)
                    ),
                )
            },
            as_of=AS_OF,
        )
        future = mi.build_profile(
            "future/model",
            {
                "reasoning": claim(
                    "reasoning",
                    evidence_record=evidence(
                        "ev-future", observed_at=AS_OF + timedelta(minutes=1)
                    ),
                )
            },
            as_of=AS_OF,
        )
        conflicted = mi.build_profile(
            "conflicted/model",
            [
                claim("reasoning", score=7, evidence_record=evidence("ev-7")),
                claim("reasoning", score=9, evidence_record=evidence("ev-9")),
            ],
            as_of=AS_OF,
        )

        self.assertEqual(stale.status, mi.STATUS_STALE)
        self.assertEqual(future.status, mi.STATUS_UNKNOWN)
        self.assertEqual(conflicted.status, mi.STATUS_CONFLICTED)
        self.assertNotIn("reasoning", conflicted.claims)

    def test_yaml_cache_requires_v1_registry_and_claim_references(self):
        yaml_text = """
schema_version: 1
evidence:
  - id: ev-cache
    source_type: fixture
    strength: HIGH
    locator: urn:fixture:cache
    observed_at: '2026-08-25T11:00:00+00:00'
    summary: cache fixture
models:
  - identity: provider/model
    claims:
      - capability: reasoning
        score: 8
        confidence: HIGH
        evidence_ids: [ev-cache]
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.yaml"
            path.write_text(yaml_text, encoding="utf-8")
            loaded = mi.load_intelligence_cache(path)
            profiles = mi.profiles_from_cache(loaded, as_of=AS_OF)

        self.assertEqual(profiles[0].identity.raw, "provider/model")
        self.assertEqual(profiles[0].claims["reasoning"].confidence, "HIGH")
        self.assertEqual(
            profiles[0].claims["reasoning"].evidence_ids, ("ev-cache",)
        )
        with self.assertRaises(TypeError):
            loaded["new"] = 1  # type: ignore[index]

    def test_cache_rejects_missing_duplicate_and_dangling_evidence_ids(self):
        base = cache_payload()
        missing = cache_payload(
            models=[
                {
                    "identity": "provider/model",
                    "claims": [
                        {
                            "capability": "reasoning",
                            "score": 8,
                            "confidence": "HIGH",
                        }
                    ],
                }
            ]
        )
        dangling = cache_payload(
            models=[
                {
                    "identity": "provider/model",
                    "claims": [
                        {
                            "capability": "reasoning",
                            "score": 8,
                            "confidence": "HIGH",
                            "evidence_ids": ["not-present"],
                        }
                    ],
                }
            ]
        )
        duplicate = cache_payload(
            evidence_entries=[base["evidence"][0], base["evidence"][0]]  # type: ignore[index]
        )
        for payload in (missing, dangling, duplicate):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    mi.profiles_from_cache(payload, as_of=AS_OF)

    def test_cache_rejects_duplicate_exact_identity_but_allows_normalized_collision(self):
        entries = [
            {
                "identity": "provider/model",
                "claims": [
                    {
                        "capability": "reasoning",
                        "score": 8,
                        "confidence": "HIGH",
                        "evidence_ids": ["ev-cache"],
                    }
                ],
            },
            {
                "identity": " provider/model ",
                "claims": [
                    {
                        "capability": "reasoning",
                        "score": 8,
                        "confidence": "HIGH",
                        "evidence_ids": ["ev-cache"],
                    }
                ],
            },
        ]
        profiles = mi.profiles_from_cache(cache_payload(models=entries), as_of=AS_OF)
        self.assertEqual(
            [item.identity.raw for item in profiles],
            ["provider/model", " provider/model "],
        )
        with self.assertRaises(ValueError):
            mi.profiles_from_cache(cache_payload(models=entries[:1] * 2), as_of=AS_OF)

    def test_recommendations_require_half_role_coverage_and_use_mapped_confidence(self):
        full = mi.build_profile(
            "full/model",
            {
                "reasoning": claim("reasoning", confidence=mi.CONFIDENCE_HIGH),
                "analysis": claim(
                    "analysis",
                    confidence=mi.CONFIDENCE_HIGH,
                    evidence_record=evidence("ev-analysis"),
                ),
                "long_context": claim(
                    "long_context",
                    confidence=mi.CONFIDENCE_HIGH,
                    evidence_record=evidence("ev-context"),
                ),
                "coding": claim(
                    "coding",
                    confidence=mi.CONFIDENCE_HIGH,
                    evidence_record=evidence("ev-coding"),
                ),
            },
            as_of=AS_OF,
        )
        partial = mi.build_profile(
            "partial/model",
            {"reasoning": claim("reasoning", score=10, confidence=mi.CONFIDENCE_HIGH)},
            as_of=AS_OF,
        )
        half = mi.build_profile(
            "half/model",
            {
                "reasoning": claim("reasoning", confidence=mi.CONFIDENCE_HIGH),
                "analysis": claim(
                    "analysis",
                    confidence=mi.CONFIDENCE_LOW,
                    evidence_record=evidence("ev-half-analysis"),
                ),
            },
            as_of=AS_OF,
        )
        result = mi.recommend_roles([full, partial, half], "planner")

        self.assertEqual(
            [item.identity.raw for item in result], ["full/model", "half/model"]
        )
        self.assertEqual(result[0].coverage, 1.0)
        self.assertEqual(result[1].coverage, 0.65)
        self.assertAlmostEqual(result[0].confidence, 0.9)

    def test_module_has_no_runtime_or_network_execution_hooks(self):
        source = inspect.getsource(mi)
        for forbidden in (
            "subprocess",
            "socket",
            "requests",
            "urllib.request",
            "importlib",
            "eval(",
            "exec(",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("models.yaml", source)


def dataclass_frozen_error():
    """Avoid importing an implementation detail solely for this assertion."""
    from dataclasses import FrozenInstanceError

    return FrozenInstanceError


if __name__ == "__main__":
    unittest.main()
