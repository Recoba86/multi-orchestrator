#!/usr/bin/env python3
"""Tests for the configure_models CLI and safe mutation workflow."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "scripts" / "configure_models.py"


class ConfigureModelsCliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(CLI_PATH), *args],
            cwd=Path(tempfile.gettempdir()),
            text=True,
            capture_output=True,
            check=False,
        )

    def sample_config(self):
        return {
            "planner": {
                "requires": ["plan"],
                "preferred": ["gpt-5.6-sol", "gpt-5.6-luna"],
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

    def write_config(self, tmpdir, data=None):
        cfg = Path(tmpdir) / "models.yaml"
        if data is None:
            data = self.sample_config()
        cfg.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return cfg

    def test_help_output(self):
        res = self.run_cli("--help")
        self.assertEqual(res.returncode, 0)
        self.assertIn("--config", res.stdout)
        self.assertIn("--set", res.stdout)
        self.assertIn("--apply", res.stdout)
        self.assertIn("--approve", res.stdout)
        self.assertIn("--expected-sha256", res.stdout)

    def test_read_mode_displays_current_preferred(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self.write_config(tmpdir)
            res = self.run_cli("--config", str(cfg))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("Current preferred roles:", res.stdout)
            self.assertIn("planner: gpt-5.6-sol", res.stdout)
            self.assertIn("scout: s1", res.stdout)

    def test_dry_run_is_default_and_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self.write_config(tmpdir)
            before_bytes = cfg.read_bytes()

            res = self.run_cli(
                "--config", str(cfg),
                "--set", "planner=gpt-5.6-luna",
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("DRY RUN (no changes written):", res.stdout)
            self.assertIn("planner -> gpt-5.6-luna", res.stdout)
            self.assertEqual(cfg.read_bytes(), before_bytes)

    def test_apply_without_approve_or_sha_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self.write_config(tmpdir)
            before_bytes = cfg.read_bytes()

            res = self.run_cli(
                "--config", str(cfg),
                "--set", "planner=gpt-5.6-luna",
                "--apply",
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("ERROR:", res.stderr)
            self.assertEqual(cfg.read_bytes(), before_bytes)

    def test_apply_with_wrong_sha_fails_closed_before_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self.write_config(tmpdir)
            before_bytes = cfg.read_bytes()

            res = self.run_cli(
                "--config", str(cfg),
                "--set", "planner=gpt-5.6-luna",
                "--apply",
                "--approve",
                "--expected-sha256", "wrongsha256",
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("ERROR:", res.stderr)
            self.assertIn("SHA-256 mismatch", res.stderr)
            self.assertEqual(cfg.read_bytes(), before_bytes)
            # No backup created
            backups = list(Path(tmpdir).glob("models.yaml.bak.*"))
            self.assertEqual(len(backups), 0)

    def test_apply_with_exact_sha_and_approval_succeeds(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self.write_config(tmpdir)
            before_bytes = cfg.read_bytes()
            sha = hashlib.sha256(before_bytes).hexdigest()

            res = self.run_cli(
                "--config", str(cfg),
                "--set", "planner=gpt-5.6-luna",
                "--apply",
                "--approve",
                "--expected-sha256", sha,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("Configuration applied successfully:", res.stdout)
            self.assertIn(f"Before SHA-256: {sha}", res.stdout)

            # File has changed
            after_data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            self.assertEqual(after_data["planner"]["preferred"], ["gpt-5.6-luna", "gpt-5.6-sol"])

            # Backup exists and matches original bytes
            backups = list(Path(tmpdir).glob("models.yaml.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), before_bytes)

    def test_duplicate_role_assignment_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self.write_config(tmpdir)
            res = self.run_cli(
                "--config", str(cfg),
                "--set", "planner=m1",
                "--set", "planner=m2",
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("duplicate assignment", res.stderr.lower())

    def test_symlink_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = self.write_config(tmpdir)
            symlink = Path(tmpdir) / "symlink.yaml"
            symlink.symlink_to(cfg)

            res = self.run_cli("--config", str(symlink))
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("symlink", res.stderr.lower())


if __name__ == "__main__":
    unittest.main()
