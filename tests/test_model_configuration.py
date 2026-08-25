#!/usr/bin/env python3
"""Tests for the declarative, provider-agnostic model-role configuration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "models.yaml"
ROLES = ("planner", "scout", "worker", "reviewer")
ROLE_FIELDS = ("requires", "preferred", "fallback", "capability_hints")


def load_model_configuration() -> dict:
    """Load the source YAML without adding a production parser or resolver."""
    with CONFIG_PATH.open(encoding="utf-8") as source:
        value = yaml.safe_load(source)
    return value


def validate_model_configuration(value: object) -> dict:
    """Validate the small public schema used by this phase's config file."""
    if not isinstance(value, dict):
        raise ValueError("configuration root must be a mapping")

    keys = set(value)
    expected_roles = set(ROLES)
    unknown_roles = keys - expected_roles
    if unknown_roles:
        raise ValueError(f"unknown top-level keys or roles: {sorted(unknown_roles)}")
    missing_roles = expected_roles - keys
    if missing_roles:
        raise ValueError(f"missing roles: {sorted(missing_roles)}")

    expected_fields = set(ROLE_FIELDS)
    for role in ROLES:
        entry = value[role]
        if not isinstance(entry, dict):
            raise ValueError(f"{role} must be a mapping")
        unknown_fields = set(entry) - expected_fields
        if unknown_fields:
            raise ValueError(f"{role} has unknown fields: {sorted(unknown_fields)}")
        missing_fields = expected_fields - set(entry)
        if missing_fields:
            raise ValueError(f"{role} is missing fields: {sorted(missing_fields)}")
        for field in ROLE_FIELDS:
            items = entry[field]
            if not isinstance(items, list) or not items:
                raise ValueError(f"{role}.{field} must be a non-empty list")
            if any(not isinstance(item, str) or not item.strip() for item in items):
                raise ValueError(f"{role}.{field} must contain non-empty strings")
    return value


class ModelConfigurationTests(unittest.TestCase):
    def test_valid_configuration_has_exact_roles_and_fields(self):
        configuration = validate_model_configuration(load_model_configuration())

        self.assertEqual(set(configuration), set(ROLES))
        for role in ROLES:
            self.assertEqual(set(configuration[role]), set(ROLE_FIELDS))

    def test_missing_roles_are_rejected(self):
        configuration = load_model_configuration()
        for role in ROLES:
            with self.subTest(role=role):
                candidate = deepcopy(configuration)
                candidate.pop(role)
                with self.assertRaisesRegex(ValueError, "missing roles"):
                    validate_model_configuration(candidate)

    def test_invalid_schema_types_and_empty_values_are_rejected(self):
        cases = (
            (None, "configuration root"),
            (("planner", "requires", "planning"), "non-empty list"),
            (("scout", "preferred", []), "non-empty list"),
            (("worker", "fallback", [""]), "non-empty strings"),
            (("reviewer", "capability_hints", [None]), "non-empty strings"),
        )
        for mutation, message in cases:
            with self.subTest(message=message):
                candidate = [] if mutation is None else deepcopy(load_model_configuration())
                if mutation is not None:
                    role, field, value = mutation
                    candidate[role][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate_model_configuration(candidate)

    def test_preferred_and_fallback_order_is_preserved(self):
        configuration = validate_model_configuration(load_model_configuration())
        expected_preferred = {
            "planner": ["gpt-5.6-sol", "nine-router/gcli/grok-4.6-high"],
            "scout": ["nine-router/ag/gemini-3.7-flash-high"],
            "worker": ["nine-router/ag/gemini-3.7-flash-high"],
            "reviewer": [
                "opencode-go-responses/gpt-5.6-luna",
                "nine-router/ag/claude-opus-4-6-thinking",
            ],
        }
        expected_fallbacks = {
            "planner": ["gpt-5.6-luna", "opencode-go/deepseek-v4-pro"],
            "scout": ["opencode-go/deepseek-v4-flash", "gpt-5.6-luna"],
            "worker": ["gpt-5.6-luna", "opencode-go/deepseek-v4-flash"],
            "reviewer": [
                "opencode-go/deepseek-v4-pro",
                "nine-router/ag/gemini-3.7-flash-high",
            ],
        }

        for role in ROLES:
            with self.subTest(role=role):
                self.assertEqual(configuration[role]["preferred"], expected_preferred[role])
                fallback = configuration[role]["fallback"]
                self.assertEqual(fallback, expected_fallbacks[role])
                # Validation must not sort or deduplicate user order.
                ordered = ["first", "second"]
                candidate = deepcopy(configuration)
                candidate[role]["fallback"] = ordered
                self.assertEqual(validate_model_configuration(candidate)[role]["fallback"], ordered)

    def test_unknown_top_level_keys_roles_and_role_fields_are_rejected(self):
        cases = (
            ("metadata", "unknown top-level keys or roles"),
            ("critic", "unknown top-level keys or roles"),
        )
        for key, message in cases:
            with self.subTest(key=key):
                candidate = deepcopy(load_model_configuration())
                candidate[key] = {}
                with self.assertRaisesRegex(ValueError, message):
                    validate_model_configuration(candidate)

        candidate = deepcopy(load_model_configuration())
        candidate["planner"]["temperature"] = ["0"]
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            validate_model_configuration(candidate)


if __name__ == "__main__":
    unittest.main()
