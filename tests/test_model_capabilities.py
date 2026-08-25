#!/usr/bin/env python3
"""Focused tests for read-only model capability metadata."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.model_capabilities import (  # noqa: E402
    CAPABILITY_LABELS,
    BUILTIN_CAPABILITY_PROFILES,
    assess_role_compatibility,
    capability_hints_for_role,
    lookup_model_capabilities,
)


class ModelCapabilityTests(unittest.TestCase):
    def test_stable_labels_are_exact_and_ordered(self):
        self.assertEqual(
            CAPABILITY_LABELS,
            (
                "reasoning",
                "coding",
                "fast",
                "long_context",
                "analysis",
                "review",
                "cost_effective",
            ),
        )

    def test_builtin_lookup_keeps_exact_model_and_provenance(self):
        metadata = lookup_model_capabilities("gpt-5.6-sol")

        self.assertEqual(metadata.model, "gpt-5.6-sol")
        self.assertEqual(metadata.status, "KNOWN")
        self.assertEqual(metadata.provenance, "builtin-profile")
        self.assertIn("reasoning", metadata.capabilities)

    def test_lookup_is_exact_without_alias_or_fuzzy_matching(self):
        exact = lookup_model_capabilities("gpt-5.6-luna")
        altered = lookup_model_capabilities("GPT-5.6-LUNA")
        extended = lookup_model_capabilities("gpt-5.6-luna-extra")

        self.assertEqual(exact.status, "KNOWN")
        self.assertEqual(altered.status, "UNKNOWN")
        self.assertEqual(extended.status, "UNKNOWN")

    def test_unknown_metadata_is_not_incompatible(self):
        metadata = lookup_model_capabilities("provider/not-in-catalog")
        compatibility = assess_role_compatibility(
            "provider/not-in-catalog", ("reasoning", "coding")
        )

        self.assertEqual(metadata.status, "UNKNOWN")
        self.assertEqual(metadata.provenance, "metadata-unavailable")
        self.assertEqual(compatibility.status, "UNKNOWN")
        self.assertEqual(compatibility.provenance, "metadata-unavailable")
        self.assertEqual(compatibility.missing, ())

    def test_role_compatibility_is_advisory_metadata(self):
        compatible = assess_role_compatibility("gpt-5.6-sol", ("reasoning",))
        incompatible = assess_role_compatibility("opencode-go/deepseek-v4-flash", ("review",))

        self.assertEqual(compatible.status, "COMPATIBLE")
        self.assertEqual(incompatible.status, "INCOMPATIBLE")
        self.assertEqual(incompatible.missing, ("review",))

    def test_role_hints_are_preserved_without_normalization(self):
        configuration = {
            "planner": {"capability_hints": ["reasoning", " custom-label "]},
        }

        self.assertEqual(
            capability_hints_for_role(configuration, "planner"),
            ("reasoning", " custom-label "),
        )

    def test_builtin_profiles_are_not_mutated_by_lookup(self):
        before = dict(BUILTIN_CAPABILITY_PROFILES)
        lookup_model_capabilities("gpt-5.6-sol")
        self.assertEqual(dict(BUILTIN_CAPABILITY_PROFILES), before)


if __name__ == "__main__":
    unittest.main()
