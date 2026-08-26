"""Tests for persistent SolMode/GrokMode state and the manual CLI.

Covers committed plan Task 1: deterministic default, exact round-trips,
switching, fail-closed malformed state, atomic writes, restrictive
permissions, symlink rejection, read-only status, CLI exit codes.

MANUAL_ONLY invariant: no function here or in the module under test may
change persisted mode as a side effect of a read; only write_mode (operator)
mutates state.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from core.runtime_routing_mode import (  # noqa: E402
    GROK_MODE,
    SOL_MODE,
    RoutingMode,
    parse_mode,
    read_mode,
    write_mode,
)

CLI = REPO_ROOT / "scripts" / "orchestrator_mode.py"


def _state(tmp: str) -> Path:
    return Path(tmp) / "runtime-routing" / "mode.json"


class ModeEnumTests(unittest.TestCase):
    def test_exactly_two_modes_with_canonical_values(self):
        self.assertEqual(RoutingMode.SOL_MODE.value, "sol_mode")
        self.assertEqual(RoutingMode.GROK_MODE.value, "grok_mode")
        self.assertEqual(len(RoutingMode), 2)

    def test_parse_exact_values_only(self):
        self.assertEqual(parse_mode("sol_mode"), SOL_MODE)
        self.assertEqual(parse_mode("grok_mode"), GROK_MODE)

    def test_parse_rejects_aliases_and_junk(self):
        for bad in (
            "", "SolMode", "GrokMode", "solmode", "SOLMODE", "grok", "Sol",
            "Grok", "sol", "banana",
        ):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_mode(bad)


class ModeStateTests(unittest.TestCase):
    """Committed plan Step 1 tests (verbatim) plus fail-closed extensions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = _state(self.tmp.name)

    def test_missing_state_defaults_sol_and_records_anomaly(self):
        self.assertEqual(read_mode(self.path), RoutingMode.SOL_MODE)
        self.assertTrue(Path(str(self.path) + ".anomaly").exists())

    def test_roundtrip_grok(self):
        write_mode(RoutingMode.GROK_MODE, self.path)
        self.assertEqual(read_mode(self.path), RoutingMode.GROK_MODE)

    def test_corrupt_state_defaults_sol(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(read_mode(self.path), RoutingMode.SOL_MODE)

    def test_unknown_mode_value_defaults_sol(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"mode": "banana"}), encoding="utf-8")
        self.assertEqual(read_mode(self.path), RoutingMode.SOL_MODE)

    def test_roundtrip_sol_explicit_persist_reload(self):
        write_mode(SOL_MODE, self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["mode"], "sol_mode")
        self.assertEqual(raw["version"], 1)
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_switch_sol_to_grok_persists(self):
        write_mode(SOL_MODE, self.path)
        write_mode(GROK_MODE, self.path)
        self.assertEqual(read_mode(self.path), GROK_MODE)
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["mode"],
            "grok_mode",
        )

    def test_switch_grok_to_sol_persists(self):
        write_mode(GROK_MODE, self.path)
        write_mode(SOL_MODE, self.path)
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_invalid_write_argument_rejected_state_unchanged(self):
        write_mode(GROK_MODE, self.path)
        before = self.path.read_bytes()
        for bad in ("SolMode", "SOLMODE", "grok", "Sol", "", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                write_mode(bad, self.path)  # type: ignore[arg-type]
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(read_mode(self.path), GROK_MODE)

    def test_malformed_json_fails_closed_to_sol_with_anomaly(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[1, 2", encoding="utf-8")
        self.assertEqual(read_mode(self.path), SOL_MODE)
        anomaly = json.loads(
            Path(str(self.path) + ".anomaly").read_text(encoding="utf-8")
        )
        self.assertEqual(anomaly["reason"], "corrupt")

    def test_unsupported_version_fails_closed_to_sol(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"version": 99, "mode": "grok_mode"}),
            encoding="utf-8",
        )
        self.assertEqual(read_mode(self.path), SOL_MODE)
        anomaly = json.loads(
            Path(str(self.path) + ".anomaly").read_text(encoding="utf-8")
        )
        self.assertEqual(anomaly["reason"], "unsupported_version")

    def test_non_string_mode_fails_closed_to_sol(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"version": 1, "mode": 7}),
                             encoding="utf-8")
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_missing_version_treated_as_v1(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"mode": "grok_mode"}),
                             encoding="utf-8")
        self.assertEqual(read_mode(self.path), GROK_MODE)

    def test_unexpected_schema_shape_fails_closed_to_sol(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"version": 1, "mode": "grok_mode",
                                         "extra": True}), encoding="utf-8")
        self.assertEqual(read_mode(self.path), SOL_MODE)
        self.path.write_text(json.dumps(["not", "a", "dict"]),
                             encoding="utf-8")
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_read_never_writes_state_file(self):
        # Read-only guarantee: missing state stays missing after read_mode.
        result = read_mode(self.path)
        self.assertEqual(result, SOL_MODE)
        self.assertFalse(self.path.exists())

    def test_state_file_permissions_restrictive(self):
        write_mode(SOL_MODE, self.path)
        mode_bits = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode_bits, 0o600)


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = _state(self.tmp.name)

    def test_no_temp_files_left_behind(self):
        write_mode(GROK_MODE, self.path)
        siblings = [p.name for p in self.path.parent.iterdir()]
        self.assertEqual(siblings, ["mode.json"])

    def test_replace_semantics_preserve_single_file(self):
        write_mode(SOL_MODE, self.path)
        inode_before = os.stat(self.path).st_ino
        write_mode(GROK_MODE, self.path)
        inode_after = os.stat(self.path).st_ino
        # os.replace swaps the file: new inode proves replace, not rewrite.
        self.assertNotEqual(inode_before, inode_after)
        self.assertEqual(read_mode(self.path), GROK_MODE)

    def test_symlinked_state_file_is_rejected_on_write(self):
        self.path.parent.mkdir(parents=True)
        target = self.path.parent / "innocent.txt"
        target.write_text("do not clobber", encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaises(RuntimeError):
            write_mode(GROK_MODE, self.path)
        self.assertEqual(target.read_text(encoding="utf-8"), "do not clobber")

    def test_symlinked_state_file_is_not_followed_on_read(self):
        self.path.parent.mkdir(parents=True)
        target = self.path.parent / "real.json"
        target.write_text(
            json.dumps({"version": 1, "mode": "grok_mode"}), encoding="utf-8"
        )
        self.path.symlink_to(target)
        # Fail closed: a symlinked authoritative path is treated as invalid.
        self.assertEqual(read_mode(self.path), SOL_MODE)


class ModeCliTests(unittest.TestCase):
    """Committed plan CLI test (verbatim shape) + exit-code/read-only proof."""

    def run_cli(self, *args, home):
        env = dict(os.environ)
        return subprocess.run(
            [sys.executable, str(CLI),
             "--state-path", str(home / "m.json"), *args],
            capture_output=True, text=True, env=env,
        )

    def test_status_then_set_grok_then_status(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            r1 = self.run_cli("status", home=home)
            self.assertEqual(r1.returncode, 0)
            self.assertIn("sol_mode", r1.stdout)
            r2 = self.run_cli("set", "grok", home=home)
            self.assertEqual(r2.returncode, 0)
            r3 = self.run_cli("status", home=home)
            self.assertEqual(r3.returncode, 0)
            self.assertIn("grok_mode", r3.stdout)

    def test_set_sol_then_set_grok_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.run_cli("set", "sol", home=home)
            r = self.run_cli("set", "grok", home=home)
            self.assertEqual(r.returncode, 0)
            self.assertIn("grok_mode", r.stdout)
            self.assertEqual(
                json.loads((home / "m.json").read_text())["mode"], "grok_mode"
            )

    def test_invalid_invocation_exits_nonzero_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.run_cli("set", "grok", home=home)
            before = (home / "m.json").read_bytes()
            for bad_args in (("set", "banana"), ("set", "SolMode"),
                             ("set",), ("frobnicate",)):
                r = self.run_cli(*bad_args, home=home)
                self.assertNotEqual(r.returncode, 0, msg=str(bad_args))
            self.assertEqual((home / "m.json").read_bytes(), before)

    def test_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.run_cli("set", "grok", home=home)
            before = (home / "m.json").read_bytes()
            listing_before = sorted(p.name for p in home.iterdir())
            r = self.run_cli("status", home=home)
            self.assertEqual(r.returncode, 0)
            self.assertEqual((home / "m.json").read_bytes(), before)
            self.assertEqual(sorted(p.name for p in home.iterdir()),
                             listing_before)

    def test_cli_rejects_alias_spellings(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            for alias in ("SolMode", "GrokMode", "solmode"):
                r = self.run_cli("set", alias, home=home)
                self.assertNotEqual(r.returncode, 0, msg=alias)


class NoRoutingMutationTests(unittest.TestCase):
    """Mission check 15: Task 1 mutates no routing policy surfaces."""

    def test_module_import_does_not_touch_repo_policy_files(self):
        tracked = [
            "core/ORCHESTRATOR_CORE.md", "core/model_policy.py",
            "core/model_resolver.py", "config/models.yaml",
            "skills/sol-luna-orchestrator-v2/SKILL.md",
            "skills/grok-orchestrator-v2/SKILL.md",
            "scripts/installer_lifecycle.py", "scripts/verify.sh",
        ]
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", *tracked],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        self.assertEqual(diff.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
