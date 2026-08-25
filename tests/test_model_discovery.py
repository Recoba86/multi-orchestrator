#!/usr/bin/env python3
"""Focused tests for read-only Codex model discovery."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.model_discovery import discover_codex_models  # noqA: E402


class ModelDiscoveryTests(unittest.TestCase):
    def test_discovers_models_from_codex_profiles_and_agent_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex"
            agents = codex / "agents"
            agents.mkdir(parents=True)
            (codex / "planner.config.toml").write_text(
                'model = "provider/planner"\n', encoding="utf-8"
            )
            (agents / "worker.toml").write_text(
                'name = "worker"\nmodel = "provider/worker"\n', encoding="utf-8"
            )

            results = discover_codex_models(home)

        self.assertEqual(
            [(result.source, result.available, result.models) for result in results],
            [
                ("codex-profiles", True, ("provider/planner",)),
                ("codex-agents", True, ("provider/worker",)),
            ],
        )

    def test_missing_sources_are_reported_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            results = discover_codex_models(Path(directory))

        self.assertEqual([result.available for result in results], [False, False])
        self.assertTrue(all(result.models == () for result in results))
        self.assertTrue(all("not found" in result.detail for result in results))

    def test_malformed_source_does_not_hide_an_available_source(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex"
            agents = codex / "agents"
            agents.mkdir(parents=True)
            (codex / "broken.config.toml").write_text("model = [\n", encoding="utf-8")
            (agents / "worker.toml").write_text(
                'model = "provider/worker"\n', encoding="utf-8"
            )

            profiles, discovered_agents = discover_codex_models(home)

        self.assertFalse(profiles.available)
        self.assertEqual(profiles.models, ())
        self.assertIn("could not be read", profiles.detail)
        self.assertTrue(discovered_agents.available)
        self.assertEqual(discovered_agents.models, ("provider/worker",))

    def test_matching_directory_is_not_treated_as_a_declaration_file(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            profiles = home / ".codex"
            profiles.mkdir(parents=True)
            (profiles / "not-a-file.config.toml").mkdir()

            profiles_result, agents_result = discover_codex_models(home)

        self.assertFalse(profiles_result.available)
        self.assertIn("not a file", profiles_result.detail)
        self.assertFalse(agents_result.available)

    def test_model_membership_is_exact_and_keeps_declared_spelling(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            profiles = home / ".codex"
            profiles.mkdir(parents=True)
            (profiles / "models.config.toml").write_text(
                'model = "provider/model"\n', encoding="utf-8"
            )
            (profiles / "other.config.toml").write_text(
                'model = "provider/model-extra"\n', encoding="utf-8"
            )
            (profiles / "spaced.config.toml").write_text(
                'model = " provider/model "\n', encoding="utf-8"
            )

            results = discover_codex_models(home)

        self.assertTrue(results[0].available)
        self.assertEqual(
            results[0].models,
            ("provider/model", "provider/model-extra", " provider/model "),
        )
        self.assertIn("provider/model", results[0].models)
        self.assertNotIn("provider/model-ex", results[0].models)

    def test_discovery_does_not_change_source_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / ".codex" / "agents"
            agents.mkdir(parents=True)
            declaration = agents / "worker.toml"
            contents = b'model = "provider/worker"\n'
            declaration.write_bytes(contents)

            discover_codex_models(home)

            self.assertEqual(declaration.read_bytes(), contents)

    def test_whitespace_invalid_and_valid_discovery_sibling_survives_with_visible_count(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex"
            agents = codex / "agents"
            agents.mkdir(parents=True)
            (codex / "a.config.toml").write_text('model = "   "\n', encoding="utf-8")
            (codex / "b.config.toml").write_text('model = "provider/model-b"\n', encoding="utf-8")
            (codex / "c.config.toml").write_text('model = 12345\n', encoding="utf-8")
            (codex / "d.config.toml").write_text('model = "provider/model-d"\n', encoding="utf-8")

            results = discover_codex_models(home)

        profiles_result = results[0]
        self.assertTrue(profiles_result.available)
        self.assertEqual(profiles_result.models, ("provider/model-b", "provider/model-d"))
        self.assertEqual(profiles_result.detail, "2 model(s), 2 invalid declaration(s)")

    def test_all_invalid_semantic_declarations_returns_unavailable_no_valid_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex"
            codex.mkdir(parents=True)
            (codex / "empty_str.config.toml").write_text('model = ""\n', encoding="utf-8")
            (codex / "ws_str.config.toml").write_text('model = "  \t  "\n', encoding="utf-8")
            (codex / "non_str.config.toml").write_text('model = ["list"]\n', encoding="utf-8")

            results = discover_codex_models(home)

        profiles_result = results[0]
        self.assertFalse(profiles_result.available)
        self.assertEqual(profiles_result.models, ())
        self.assertEqual(profiles_result.detail, "no valid declarations")

    def test_malformed_toml_syntax_remains_source_wide_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            codex = home / ".codex"
            codex.mkdir(parents=True)
            (codex / "valid.config.toml").write_text('model = "provider/valid"\n', encoding="utf-8")
            (codex / "syntax_error.config.toml").write_text("model = [unclosed\n", encoding="utf-8")

            results = discover_codex_models(home)

        profiles_result = results[0]
        self.assertFalse(profiles_result.available)
        self.assertEqual(profiles_result.models, ())
        self.assertIn("could not be read", profiles_result.detail)


if __name__ == "__main__":
    unittest.main()
