#!/usr/bin/env python3
"""Focused tests for the declarative Orchestrator Doctor command."""

from __future__ import annotations

import builtins
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCTOR_PATH = REPO_ROOT / "scripts" / "doctor.py"
CONFIG_PATH = REPO_ROOT / "config" / "models.yaml"
ROLES = ("planner", "scout", "worker", "reviewer")
FIELDS = ("requires", "preferred", "fallback", "capability_hints")
AS_OF = datetime(2026, 8, 25, 12, tzinfo=timezone.utc)


def load_doctor_module():
    spec = importlib.util.spec_from_file_location("orchestrator_doctor", DOCTOR_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load doctor module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DoctorCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doctor = load_doctor_module()

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(DOCTOR_PATH), *args],
            cwd=Path(tempfile.gettempdir()),
            text=True,
            capture_output=True,
            check=False,
        )

    def write_config(self, value):
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        with handle:
            yaml.safe_dump(value, handle, sort_keys=False)
        return Path(handle.name)

    def write_cache(self, value):
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        with handle:
            yaml.safe_dump(value, handle, sort_keys=False)
        return Path(handle.name)

    def intelligence_cache(self, models):
        return {
            "schema_version": 1,
            "evidence": [
                {
                    "id": "ev-active",
                    "source_type": "fixture",
                    "strength": "HIGH",
                    "locator": "urn:fixture:doctor",
                    "observed_at": "2026-08-25T01:00:00+00:00",
                    "summary": "doctor fixture",
                }
            ],
            "models": models,
        }

    def model_entry(self, identity, claims):
        return {"identity": identity, "claims": claims}

    def claim(self, capability="reasoning", score=8, confidence="HIGH", evidence_id="ev-active"):
        return {
            "capability": capability,
            "score": score,
            "confidence": confidence,
            "evidence_ids": [evidence_id],
        }

    def discovered_home(self, *models):
        handle = tempfile.TemporaryDirectory()
        self.addCleanup(handle.cleanup)
        agents = Path(handle.name) / ".codex" / "agents"
        agents.mkdir(parents=True)
        for index, model in enumerate(models):
            (agents / f"model-{index}.toml").write_text(
                f"model = {model!r}\n", encoding="utf-8"
            )
        return Path(handle.name)

    def test_default_config_prints_stable_role_model_and_capability_output(self):
        result = self.run_cli()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("recommendations/configuration only", result.stdout)
        self.assertIn("no provider or runtime probing", result.stdout)
        self.assertIn("discovery does not select models", result.stdout)
        positions = [result.stdout.index(f"Role: {role}") for role in ROLES]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Preferred models:", result.stdout)
        self.assertIn("Fallback models:", result.stdout)
        self.assertIn("Capability hints:", result.stdout)

    def test_capability_metadata_and_compatibility_are_explicitly_advisory(self):
        result = self.run_cli("--target-home", tempfile.gettempdir())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Capability metadata and compatibility are advisory only", result.stdout)
        for claim in (
            "provider health",
            "authentication",
            "entitlement",
            "runtime availability",
            "effective identity",
            "authorization",
            "suitability",
        ):
            self.assertIn(claim, result.stdout)
        self.assertIn("Capabilities: reasoning", result.stdout)
        self.assertIn("Provenance: builtin-profile", result.stdout)
        self.assertIn("Compatibility: COMPATIBLE", result.stdout)

    def test_unknown_model_capability_metadata_is_reported_without_incompatibility(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        configuration["planner"]["preferred"] = ["provider/unknown"]
        result = self.run_cli("--config", str(self.write_config(configuration)))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("provider/unknown: UNKNOWN/metadata-unavailable", result.stdout)
        self.assertNotIn("provider/unknown: INCOMPATIBLE", result.stdout)

    def test_capability_reporting_does_not_mutate_configuration(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        config_path = self.write_config(configuration)
        before = config_path.read_bytes()

        result = self.run_cli("--config", str(config_path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config_path.read_bytes(), before)

    def test_configured_list_order_is_kept_in_output(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        configuration["planner"]["preferred"] = ["first/model", "second/model"]
        result = self.run_cli("--config", str(self.write_config(configuration)))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(result.stdout.index("first/model"), result.stdout.index("second/model"))

    def test_help_describes_config_override(self):
        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("--config", result.stdout)
        self.assertIn("--target-home", result.stdout)

    def test_missing_intelligence_cache_reports_unknown_discovered_models(self):
        home = self.discovered_home("provider/model")

        result = self.run_cli("--target-home", str(home))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Intelligence cache: MISSING", result.stdout)
        self.assertIn("Raw identity: provider/model", result.stdout)
        self.assertIn("Normalized identity: provider/model", result.stdout)
        self.assertIn("Status: UNKNOWN", result.stdout)
        self.assertIn("normalization is not alias resolution", result.stdout)

    def test_invalid_intelligence_cache_is_sanitized_and_withholds_ranking(self):
        home = self.discovered_home("discovered/model")
        cache = self.write_cache({"schema_version": 1, "models": [{"identity": "secret/model"}]})

        result = self.run_cli(
            "--target-home", str(home), "--intelligence-cache", str(cache)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Intelligence cache: INVALID", result.stdout)
        self.assertIn("Advisory ranking withheld", result.stdout)
        self.assertNotIn("secret/model", result.stdout)
        self.assertNotIn("Traceback", result.stdout)

    def test_intelligence_joins_exact_raw_identities_and_reports_profile_states(self):
        home = self.discovered_home(
            "active/model", "stale/model", "conflicted/model", "unknown/model"
        )
        cache = self.write_cache(
            self.intelligence_cache(
                [
                    self.model_entry(
                        "active/model",
                        [self.claim("reasoning", score=9)],
                    ),
                    self.model_entry(
                        "stale/model",
                        [self.claim("reasoning", score=7, evidence_id="ev-stale")],
                    ),
                    self.model_entry(
                        "conflicted/model",
                        [
                            self.claim("reasoning", score=7, evidence_id="ev-conflict-a"),
                            self.claim("reasoning", score=9, evidence_id="ev-conflict-b"),
                        ],
                    ),
                    self.model_entry(
                        "unknown/model",
                        [self.claim("reasoning", score=6, evidence_id="ev-future")],
                    ),
                    self.model_entry(
                        "cache/only",
                        [
                            self.claim("reasoning", score=10),
                            self.claim("analysis", score=10),
                        ],
                    ),
                ]
            )
        )
        payload = yaml.safe_load(cache.read_text(encoding="utf-8"))
        payload["evidence"] = [
            payload["evidence"][0],
            {
                "id": "ev-stale",
                "source_type": "fixture",
                "strength": "LOW",
                "locator": "urn:fixture:stale",
                "observed_at": "2026-08-25T00:00:00+00:00",
                "expires_at": "2026-08-25T02:00:00+00:00",
                "summary": "stale fixture",
            },
            {
                "id": "ev-conflict-a",
                "source_type": "fixture",
                "strength": "HIGH",
                "locator": "urn:fixture:conflict-a",
                "observed_at": "2026-08-25T01:00:00+00:00",
                "summary": "conflict fixture a",
            },
            {
                "id": "ev-conflict-b",
                "source_type": "fixture",
                "strength": "MEDIUM",
                "locator": "urn:fixture:conflict-b",
                "observed_at": "2026-08-25T01:00:00+00:00",
                "summary": "conflict fixture b",
            },
            {
                "id": "ev-future",
                "source_type": "fixture",
                "strength": "MEDIUM",
                "locator": "urn:fixture:future",
                "observed_at": "2026-08-25T13:00:00+00:00",
                "summary": "future fixture",
            },
        ]
        cache.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

        result = self.run_cli(
            "--target-home", str(home), "--intelligence-cache", str(cache)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Intelligence cache: VALID", result.stdout)
        for model, status in (
            ("active/model", "ACTIVE"),
            ("stale/model", "STALE"),
            ("conflicted/model", "CONFLICTED"),
            ("unknown/model", "UNKNOWN"),
        ):
            self.assertIn(f"Raw identity: {model}", result.stdout)
            self.assertIn(f"Status: {status}", result.stdout)
        self.assertIn("score=9", result.stdout)
        self.assertIn("confidence=HIGH", result.stdout)
        self.assertIn("evidence_ids=ev-active", result.stdout)
        self.assertIn("strength=HIGH", result.stdout)
        self.assertIn("provenance=fixture", result.stdout)
        self.assertIn("NOT_DISCOVERED", result.stdout)
        self.assertNotIn("cache/only: score", result.stdout)
        self.assertIn("Advisory recommendations", result.stdout)
        self.assertIn("planner", result.stdout)

    def test_intelligence_exact_matching_does_not_resolve_normalized_aliases(self):
        home = self.discovered_home(" provider/model ")
        cache = self.write_cache(
            self.intelligence_cache(
                [self.model_entry("provider/model", [self.claim()])]
            )
        )

        result = self.run_cli(
            "--target-home", str(home), "--intelligence-cache", str(cache)
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Raw identity:  provider/model ", result.stdout)
        self.assertIn("Status: UNKNOWN", result.stdout)
        self.assertIn("Raw identity: provider/model", result.stdout)
        self.assertIn("NOT_DISCOVERED", result.stdout)

    def test_intelligence_rendering_is_deterministic_for_injected_utc(self):
        home = self.discovered_home("provider/model")
        cache = self.write_cache(
            self.intelligence_cache(
                [self.model_entry("provider/model", [self.claim()])]
            )
        )
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        discovery = self.doctor.discover_codex_models(home)
        first = self.doctor.render_model_intelligence(
            discovery,
            configuration,
            cache,
            as_of=AS_OF,
        )
        second = self.doctor.render_model_intelligence(
            discovery,
            configuration,
            cache,
            as_of=AS_OF,
        )

        self.assertEqual(first, second)

    def test_intelligence_reporting_does_not_mutate_cache_or_configuration(self):
        home = self.discovered_home("provider/model")
        cache = self.write_cache(
            self.intelligence_cache(
                [self.model_entry("provider/model", [self.claim()])]
            )
        )
        config = self.write_config(yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")))
        cache_before = cache.read_bytes()
        config_before = config.read_bytes()

        result = self.run_cli(
            "--config", str(config),
            "--target-home", str(home),
            "--intelligence-cache", str(cache),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cache.read_bytes(), cache_before)
        self.assertEqual(config.read_bytes(), config_before)

    def test_discovery_is_compared_with_configured_models(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        configuration["planner"]["preferred"] = ["provider/available", "provider/missing"]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            agents = home / ".codex" / "agents"
            agents.mkdir(parents=True)
            (agents / "planner.toml").write_text(
                'model = "provider/available"\n', encoding="utf-8"
            )

            result = self.run_cli(
                "--config", str(self.write_config(configuration)), "--target-home", str(home)
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Discovery source codex-profiles: UNAVAILABLE", result.stdout)
        self.assertIn("Discovery source codex-agents: AVAILABLE", result.stdout)
        self.assertIn("provider/available: declared", result.stdout)
        self.assertIn("provider/missing: configured but not declared", result.stdout)

    def test_capability_reporting_preserves_discovery_availability_and_exact_identifiers(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        configuration["planner"]["preferred"] = [" provider/model "]
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            profiles = home / ".codex"
            profiles.mkdir(parents=True)
            (profiles / "planner.config.toml").write_text(
                'model = " provider/model "\n', encoding="utf-8"
            )

            result = self.run_cli(
                "--config", str(self.write_config(configuration)), "--target-home", str(home)
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Discovery source codex-profiles: AVAILABLE", result.stdout)
        self.assertIn("    provider/model : declared", result.stdout)
        self.assertIn(" provider/model : UNKNOWN/metadata-unavailable", result.stdout)

    def test_unavailable_discovery_does_not_fail_valid_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli("--target-home", directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Configuration: valid", result.stdout)
        self.assertEqual(result.stdout.count("Discovery source "), 2)
        self.assertEqual(result.stdout.count(": UNAVAILABLE"), 2)
        self.assertIn("configured but not declared", result.stdout)

    def test_non_file_source_entry_is_unavailable_without_failing_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".codex").mkdir()
            (home / ".codex" / "not-a-file.config.toml").mkdir()

            result = self.run_cli("--target-home", str(home))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Discovery source codex-profiles: UNAVAILABLE", result.stdout)
        self.assertIn("source path is not a file", result.stdout)

    def test_missing_config_is_a_concise_error(self):
        result = self.run_cli("--config", "/path/that/does/not/exist/models.yaml")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR:", result.stderr)
        self.assertIn("not found", result.stderr.lower())
        self.assertNotIn("planner:", result.stderr)

    def test_unreadable_config_is_a_concise_error(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli("--config", directory)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR:", result.stderr)
        self.assertIn("unreadable", result.stderr.lower())

    def test_yaml_parser_unavailable_is_fail_closed(self):
        original_import = builtins.__import__

        def unavailable(name, *args, **kwargs):
            if name == "yaml":
                raise ModuleNotFoundError("yaml is unavailable")
            return original_import(name, *args, **kwargs)

        stdout = StringIO()
        stderr = StringIO()
        with patch("builtins.__import__", unavailable), redirect_stdout(stdout), redirect_stderr(stderr):
            status = self.doctor.main(["--config", str(CONFIG_PATH)])

        self.assertNotEqual(status, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("ERROR:", stderr.getvalue())
        self.assertIn("YAML parser unavailable", stderr.getvalue())

    def test_malformed_yaml_is_a_fail_closed_error(self):
        config_path = self.write_raw("planner: [\n")

        result = self.run_cli("--config", str(config_path))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR:", result.stderr)
        self.assertIn("parse", result.stderr.lower())

    def test_non_mapping_root_is_rejected(self):
        config_path = self.write_raw("- planner\n")

        result = self.run_cli("--config", str(config_path))

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mapping", result.stderr.lower())

    def test_each_required_role_is_checked(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        for role in ROLES:
            with self.subTest(role=role):
                candidate = deepcopy(configuration)
                candidate.pop(role)
                result = self.run_cli("--config", str(self.write_config(candidate)))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("missing required role", result.stderr.lower())
                self.assertIn(role, result.stderr)

    def test_unknown_roles_and_fields_are_rejected(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

        unknown_role = deepcopy(configuration)
        unknown_role["critic"] = deepcopy(configuration["planner"])
        result = self.run_cli("--config", str(self.write_config(unknown_role)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown role", result.stderr.lower())

        unknown_field = deepcopy(configuration)
        unknown_field["planner"]["temperature"] = ["0"]
        result = self.run_cli("--config", str(self.write_config(unknown_field)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown field", result.stderr.lower())

    def test_each_role_rejects_empty_preferred_and_fallback_lists(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        for role in ROLES:
            for field in ("preferred", "fallback"):
                with self.subTest(role=role, field=field):
                    candidate = deepcopy(configuration)
                    candidate[role][field] = []
                    result = self.run_cli("--config", str(self.write_config(candidate)))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("non-empty list", result.stderr.lower())

    def test_blank_and_non_string_entries_are_rejected(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        for value in ("   ", 17, None):
            with self.subTest(value=value):
                candidate = deepcopy(configuration)
                candidate["worker"]["preferred"] = [value]
                result = self.run_cli("--config", str(self.write_config(candidate)))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("non-empty strings", result.stderr.lower())

    def test_all_fields_are_required(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        for role in ROLES:
            for field in FIELDS:
                with self.subTest(role=role, field=field):
                    candidate = deepcopy(configuration)
                    candidate[role].pop(field)
                    result = self.run_cli("--config", str(self.write_config(candidate)))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("missing required field", result.stderr.lower())

    def test_model_availability_section_is_rendered_in_default_mode(self):
        result = self.run_cli("--target-home", tempfile.gettempdir())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Model availability and provider health (read-only; no network operations executed):", result.stdout)
        self.assertIn("Active probes mode: DISABLED (default). Zero active probes executed.", result.stdout)
        self.assertIn("Provider health status:", result.stdout)
        self.assertIn("Provider UNKNOWN: UNKNOWN (offline-declaration)", result.stdout)
        self.assertIn("Model availability status:", result.stdout)
        self.assertIn("detail=offline observation; no active probe", result.stdout)

    def test_active_probes_flag_reports_probe_unsupported_without_network(self):
        result = self.run_cli("--target-home", tempfile.gettempdir(), "--active-probes")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Active probes mode: ENABLED (--active-probes requested).", result.stdout)
        self.assertIn("No supported provider probe adapter exists; all probes report UNKNOWN/PROBE_UNSUPPORTED without network operations.", result.stdout)
        self.assertIn("Provider UNKNOWN: UNKNOWN (probe-unsupported)", result.stdout)
        self.assertIn("detail=no supported active probe adapter; network operations unavailable", result.stdout)



    def test_malformed_discovered_model_identifiers_are_safely_contained(self):
        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        codex = Path(home.name) / ".codex"
        agents = codex / "agents"
        agents.mkdir(parents=True)
        (agents / "agent-valid.toml").write_text("model = 'valid/sibling-model'\n", encoding="utf-8")
        (agents / "agent-c1.toml").write_text("model = 'model\\u0080_c1'\n", encoding="utf-8")
        (agents / "agent-backslash.toml").write_text("model = 'model\\\\backslash'\n", encoding="utf-8")
        (agents / "agent-long.toml").write_text("model = '" + "a" * 600 + "'\n", encoding="utf-8")

        result = self.run_cli("--target-home", home.name)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("Traceback", result.stdout)
        self.assertNotIn(chr(27), result.stdout)
        self.assertNotIn(chr(0), result.stdout)
        self.assertNotIn(chr(0x80), result.stdout)
        self.assertIn("valid/sibling-model", result.stdout)
        self.assertIn("detail=invalid-identifier", result.stdout)

    def test_doctor_discovery_sibling_preservation_and_invalid_count(self):
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        configuration["planner"]["preferred"] = ["provider/sibling-model"]
        config_file = self.write_config(configuration)

        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        codex = Path(home.name) / ".codex"
        agents = codex / "agents"
        agents.mkdir(parents=True)
        (agents / "a1.toml").write_text("model = '   '\n", encoding="utf-8")
        (agents / "a2.toml").write_text("model = 'provider/sibling-model'\n", encoding="utf-8")
        (agents / "a3.toml").write_text("model = 999\n", encoding="utf-8")

        result = self.run_cli("--config", str(config_file), "--target-home", home.name)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Discovery source codex-agents: AVAILABLE (1 model(s), 2 invalid declaration(s))", result.stdout)
        self.assertIn("provider/sibling-model: declared", result.stdout)

    def test_overlong_identifiers_bounded_across_all_doctor_sections_without_raw_full_string(self):
        long_id = "x" * 600
        configuration = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        configuration["planner"]["preferred"] = [long_id]
        config_file = self.write_config(configuration)

        home = tempfile.TemporaryDirectory()
        self.addCleanup(home.cleanup)
        codex = Path(home.name) / ".codex"
        agents = codex / "agents"
        agents.mkdir(parents=True)
        (agents / "long.toml").write_text('model = ' + repr(long_id) + chr(10), encoding="utf-8")
        (agents / "valid-sibling.toml").write_text("model = 'provider/valid-sibling'" + chr(10), encoding="utf-8")

        cache = self.write_cache(
            self.intelligence_cache(
                [self.model_entry(long_id, [self.claim("reasoning", score=9)])]
            )
        )

        result = self.run_cli(
            "--config", str(config_file),
            "--target-home", home.name,
            "--intelligence-cache", str(cache),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        # Ensure raw full 600-char identifier never appears in stdout
        self.assertNotIn(long_id, result.stdout)
        # Ensure bounded sanitized identifier (384 chars ending in ...) is present
        expected_bounded = "x" * 381 + "..."
        self.assertIn(expected_bounded, result.stdout)
        self.assertIn("...", result.stdout)

        # Ensure availability still includes UNKNOWN and invalid-identifier
        self.assertIn("detail=invalid-identifier", result.stdout)
        self.assertIn("UNKNOWN", result.stdout)

        # Ensure valid discovery sibling remains visible
        self.assertIn("provider/valid-sibling", result.stdout)

        # Assert every complete rendered output line in stdout <= 512 characters
        lines = result.stdout.splitlines()
        self.assertTrue(len(lines) > 0)
        for line in lines:
            self.assertLessEqual(len(line), 512, f"Line exceeded 512 chars (len={len(line)}): {line[:60]}...")

    def write_raw(self, contents):
        handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        with handle:
            handle.write(contents)
        return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
