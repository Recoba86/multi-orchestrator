#!/usr/bin/env python3
"""Focused tests for the centralized model-policy definitions."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core import model_policy  # noqa: E402
from core.model_capabilities import CAPABILITY_LABELS  # noqa: E402
from core.model_intelligence import (  # noqa: E402
    MIN_ROLE_COVERAGE,
    ROLE_RECOMMENDATION_WEIGHTS,
)


class ModelPolicyTests(unittest.TestCase):
    def test_public_roles_are_exact_and_ordered(self):
        self.assertEqual(
            model_policy.PUBLIC_ROLES,
            ("planner", "scout", "worker", "reviewer"),
        )

    def test_role_recognition_is_exact(self):
        for role in model_policy.PUBLIC_ROLES:
            self.assertTrue(model_policy.is_public_role(role))
        self.assertFalse(model_policy.is_public_role("PLANNER"))
        self.assertFalse(model_policy.is_public_role("boss"))
        self.assertFalse(model_policy.is_public_role(None))
        self.assertFalse(model_policy.is_public_role(1))

    def test_outcome_and_rule_vocabularies_are_stable(self):
        self.assertEqual(model_policy.OUTCOME_RECOMMENDED, "RECOMMENDED")
        self.assertEqual(model_policy.OUTCOME_UNRESOLVED, "UNRESOLVED")
        self.assertEqual(model_policy.OUTCOME_REJECTED, "REJECTED")
        self.assertEqual(model_policy.OUTCOME_UNKNOWN, "UNKNOWN")

        self.assertEqual(
            model_policy.HARD_CONSTRAINTS,
            (
                "exact_configured_identity",
                "discovered_identity",
                "availability_not_unavailable",
            ),
        )
        self.assertEqual(
            model_policy.TIE_BREAK,
            (
                "weighted_score_desc",
                "coverage_desc",
                "confidence_desc",
                "raw_identity_asc",
            ),
        )

    def test_policy_aliases_existing_sources_of_truth(self):
        self.assertIs(model_policy.ROLE_WEIGHTS, ROLE_RECOMMENDATION_WEIGHTS)
        self.assertEqual(model_policy.ROLE_COVERAGE_THRESHOLD, MIN_ROLE_COVERAGE)
        self.assertIs(model_policy.CAPABILITIES, CAPABILITY_LABELS)

    def test_configured_identifiers_preserve_order_and_deduplicate_exactly(self):
        configuration = {
            "planner": {
                "preferred": ["a/model", "b/model"],
                "fallback": ["a/model", "c/model"],
            },
        }
        self.assertEqual(
            model_policy.configured_role_identifiers(configuration, "planner"),
            ("a/model", "b/model", "c/model"),
        )

    def test_configured_identifiers_keep_exact_spelling_without_alias(self):
        configuration = {
            "planner": {
                "preferred": ["a/model", " A/model "],
                "fallback": ["A/MODEL"],
            },
        }
        self.assertEqual(
            model_policy.configured_role_identifiers(configuration, "planner"),
            ("a/model", " A/model ", "A/MODEL"),
        )

    def test_configured_identifiers_reject_unknown_role_and_bad_shape(self):
        self.assertEqual(
            model_policy.configured_role_identifiers({}, "boss"),
            (),
        )
        self.assertEqual(
            model_policy.configured_role_identifiers(
                {"planner": {"preferred": "not-a-list"}}, "planner"
            ),
            (),
        )
        self.assertEqual(model_policy.configured_role_identifiers(None, "planner"), ())

    def test_apply_role_selections_moves_to_front_of_preferred_preserving_others(self):
        config = {
            "planner": {
                "requires": ["plan"],
                "preferred": ["m1", "m2"],
                "fallback": ["f1"],
                "capability_hints": ["h1"],
            },
            "scout": {
                "requires": ["scout"],
                "preferred": ["s1"],
                "fallback": ["sf1"],
                "capability_hints": ["sh1"],
            },
            "worker": {
                "requires": ["work"],
                "preferred": ["w1"],
                "fallback": ["wf1"],
                "capability_hints": ["wh1"],
            },
            "reviewer": {
                "requires": ["rev"],
                "preferred": ["r1"],
                "fallback": ["rf1"],
                "capability_hints": ["rh1"],
            },
        }
        updated = model_policy.apply_role_selections(config, {"planner": "m2"})
        self.assertEqual(updated["planner"]["preferred"], ["m2", "m1"])
        self.assertEqual(updated["planner"]["fallback"], ["f1"])
        self.assertEqual(updated["scout"]["preferred"], ["s1"])

        # Test selecting a new model not in preferred list
        updated2 = model_policy.apply_role_selections(config, {"planner": "m3"})
        self.assertEqual(updated2["planner"]["preferred"], ["m3", "m1", "m2"])

    def test_apply_role_selections_rejects_unknown_role_and_empty_model(self):
        config = {
            "planner": {
                "requires": ["plan"],
                "preferred": ["m1"],
                "fallback": ["f1"],
                "capability_hints": ["h1"],
            },
            "scout": {
                "requires": ["scout"],
                "preferred": ["s1"],
                "fallback": ["sf1"],
                "capability_hints": ["sh1"],
            },
            "worker": {
                "requires": ["work"],
                "preferred": ["w1"],
                "fallback": ["wf1"],
                "capability_hints": ["wh1"],
            },
            "reviewer": {
                "requires": ["rev"],
                "preferred": ["r1"],
                "fallback": ["rf1"],
                "capability_hints": ["rh1"],
            },
        }
        with self.assertRaises(model_policy.ConfigurationError):
            model_policy.apply_role_selections(config, {"boss": "m1"})
        with self.assertRaises(model_policy.ConfigurationError):
            model_policy.apply_role_selections(config, {"planner": "  "})

    def test_validate_and_apply_preserve_role_and_field_mapping_order(self):
        config = {
            "reviewer": {
                "capability_hints": ["rh1"],
                "fallback": ["rf1"],
                "requires": ["rev"],
                "preferred": ["r1", "r2"],
            },
            "planner": {
                "capability_hints": ["ph1"],
                "fallback": ["pf1"],
                "requires": ["plan"],
                "preferred": ["p1", "p2"],
            },
            "worker": {
                "capability_hints": ["wh1"],
                "fallback": ["wf1"],
                "requires": ["work"],
                "preferred": ["w1"],
            },
            "scout": {
                "capability_hints": ["sh1"],
                "fallback": ["sf1"],
                "requires": ["scout"],
                "preferred": ["s1"],
            },
        }

        validated = model_policy.validate_configuration(config)
        self.assertEqual(list(validated), list(config))
        for role in config:
            self.assertEqual(list(validated[role]), list(config[role]))

        updated = model_policy.apply_role_selections(config, {"planner": "p2"})
        self.assertEqual(list(updated), list(config))
        for role in config:
            self.assertEqual(list(updated[role]), list(config[role]))
        self.assertEqual(updated["planner"]["preferred"], ["p2", "p1"])

    def test_mutation_rejects_symlinked_immediate_parent_before_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            real_parent = root / "real"
            real_parent.mkdir()
            cfg = real_parent / "models.yaml"
            cfg.write_text(yaml.safe_dump(self._sample_configuration(), sort_keys=False), encoding="utf-8")
            alias_parent = root / "alias"
            alias_parent.symlink_to(real_parent, target_is_directory=True)
            target = alias_parent / cfg.name
            before = cfg.read_bytes()
            sha = model_policy.compute_file_sha256(cfg)

            with self.assertRaisesRegex(model_policy.ConfigurationError, "symlink"):
                model_policy.mutate_configuration_file(
                    target,
                    {"planner": "m2"},
                    expected_sha256=sha,
                    dry_run=False,
                    approved=True,
                )

            self.assertEqual(cfg.read_bytes(), before)
            self.assertEqual(list(real_parent.glob("models.yaml.bak.*")), [])
            self.assertEqual(list(real_parent.glob(".models.yaml.tmp.*")), [])

    def test_malformed_emitted_bytes_fail_closed_before_backup_or_temp(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "models.yaml"
            cfg.write_text(yaml.safe_dump(self._sample_configuration(), sort_keys=False), encoding="utf-8")
            before = cfg.read_bytes()
            sha = model_policy.compute_file_sha256(cfg)

            with patch.object(yaml, "safe_dump", return_value="planner: [\n"):
                with self.assertRaises(model_policy.ConfigurationError):
                    model_policy.mutate_configuration_file(
                        cfg,
                        {"planner": "m2"},
                        expected_sha256=sha,
                        dry_run=False,
                        approved=True,
                    )

            self.assertEqual(cfg.read_bytes(), before)
            self.assertEqual(list(Path(tmpdir).glob("models.yaml.bak.*")), [])
            self.assertEqual(list(Path(tmpdir).glob(".models.yaml.tmp.*")), [])

    @staticmethod
    def _sample_configuration():
        return {
            "planner": {
                "requires": ["plan"],
                "preferred": ["m1", "m2"],
                "fallback": ["f1"],
                "capability_hints": ["h1"],
            },
            "scout": {
                "requires": ["scout"],
                "preferred": ["s1"],
                "fallback": ["sf1"],
                "capability_hints": ["sh1"],
            },
            "worker": {
                "requires": ["work"],
                "preferred": ["w1"],
                "fallback": ["wf1"],
                "capability_hints": ["wh1"],
            },
            "reviewer": {
                "requires": ["rev"],
                "preferred": ["r1"],
                "fallback": ["rf1"],
                "capability_hints": ["rh1"],
            },
        }

    def test_mutate_configuration_file_safe_atomic_flow_and_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / "models.yaml"
            data = {
                "planner": {
                    "requires": ["plan"],
                    "preferred": ["m1", "m2"],
                    "fallback": ["f1"],
                    "capability_hints": ["h1"],
                },
                "scout": {
                    "requires": ["scout"],
                    "preferred": ["s1"],
                    "fallback": ["sf1"],
                    "capability_hints": ["sh1"],
                },
                "worker": {
                    "requires": ["work"],
                    "preferred": ["w1"],
                    "fallback": ["wf1"],
                    "capability_hints": ["wh1"],
                },
                "reviewer": {
                    "requires": ["rev"],
                    "preferred": ["r1"],
                    "fallback": ["rf1"],
                    "capability_hints": ["rh1"],
                },
            }
            cfg.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
            sha = model_policy.compute_file_sha256(cfg)

            # Dry run test
            res_dry = model_policy.mutate_configuration_file(
                cfg, {"planner": "m2"}, expected_sha256=sha, dry_run=True
            )
            self.assertFalse(res_dry.applied)
            self.assertIsNone(res_dry.backup_path)

            # Apply test with wrong sha fails closed before backup
            with self.assertRaises(model_policy.ConfigurationError):
                model_policy.mutate_configuration_file(
                    cfg, {"planner": "m2"}, expected_sha256="wrong", dry_run=False, approved=True
                )
            backups = list(Path(tmpdir).glob("models.yaml.bak.*"))
            self.assertEqual(len(backups), 0)

            # Apply test with unapproved fails closed
            with self.assertRaises(model_policy.ConfigurationError):
                model_policy.mutate_configuration_file(
                    cfg, {"planner": "m2"}, expected_sha256=sha, dry_run=False, approved=False
                )

            # Valid apply mutation
            res = model_policy.mutate_configuration_file(
                cfg, {"planner": "m2"}, expected_sha256=sha, dry_run=False, approved=True
            )
            self.assertTrue(res.applied)
            self.assertIsNotNone(res.backup_path)
            self.assertTrue(res.backup_path.is_file())
            # Backup is byte exact to original
            self.assertEqual(model_policy.compute_file_sha256(res.backup_path), sha)

            # New config has m2 at front
            loaded = model_policy.load_configuration(cfg)
            self.assertEqual(loaded["planner"]["preferred"], ["m2", "m1"])


if __name__ == "__main__":
    unittest.main()
