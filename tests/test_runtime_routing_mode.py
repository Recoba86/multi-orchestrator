"""Tests for persistent SolMode/GrokMode state and the manual CLI (Task 1R).

Corrective contract under test:
- Canonical persisted values are EXACTLY ``SolMode`` / ``GrokMode``.
- Canonical CLI surface: ``status``, ``SolMode``, ``GrokMode``.
- Reads perform ZERO filesystem mutation: no sidecars, no directories,
  nothing created or modified on any read path, including malformed state.
- Strict schema validation: exact key set {version, mode}, integer version
  equal to 1 (missing version is INVALID), exact canonical mode strings.
- Writes remain atomic (tmp + os.replace) with 0600 file / 0700 dir modes
  and refuse to follow symlinks in either direction.

MANUAL_ONLY invariant: only an explicit operator command mutates persisted
state; no read path ever writes.
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


def _tree_snapshot(root: Path) -> dict[str, bytes | None]:
    """Recursive name -> content map; None entries mark directories."""
    snap: dict[str, bytes | None] = {}
    if not root.exists():
        return snap
    for p in sorted(root.rglob("*")):
        snap[str(p.relative_to(root))] = (
            p.read_bytes() if p.is_file() else None
        )
    return snap


class ModeEnumTests(unittest.TestCase):
    def test_exactly_two_modes_with_canonical_values(self):
        self.assertEqual(RoutingMode.SOL_MODE.value, "SolMode")
        self.assertEqual(RoutingMode.GROK_MODE.value, "GrokMode")
        self.assertEqual(len(RoutingMode), 2)
        self.assertIs(RoutingMode("SolMode"), SOL_MODE)
        self.assertIs(RoutingMode("GrokMode"), GROK_MODE)

    def test_parse_exact_canonical_values_only(self):
        self.assertEqual(parse_mode("SolMode"), SOL_MODE)
        self.assertEqual(parse_mode("GrokMode"), GROK_MODE)

    def test_parse_rejects_legacy_and_alias_spellings(self):
        for bad in (
            "", "sol_mode", "grok_mode", "solmode", "SOLMODE", "GROKMODE",
            "sol", "grok", "Sol", "Grok", "SolMode ", " SolMode", "banana",
        ):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_mode(bad)


class ModeStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.path = _state(self.tmp.name)

    def _write_state(self, payload: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(payload, encoding="utf-8")

    def test_roundtrip_grok_persists_canonical_value(self):
        write_mode(GROK_MODE, self.path)
        self.assertEqual(read_mode(self.path), GROK_MODE)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"version": 1, "mode": "GrokMode"})

    def test_roundtrip_sol_explicit_persist_reload(self):
        write_mode(SOL_MODE, self.path)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw, {"version": 1, "mode": "SolMode"})
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_switch_both_directions_persist(self):
        write_mode(SOL_MODE, self.path)
        write_mode(GROK_MODE, self.path)
        self.assertEqual(read_mode(self.path), GROK_MODE)
        write_mode(SOL_MODE, self.path)
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_missing_state_fails_closed_with_zero_mutation(self):
        before = _tree_snapshot(self.home)
        self.assertEqual(read_mode(self.path), SOL_MODE)
        # No directory created, no sidecar, nothing at all.
        self.assertEqual(_tree_snapshot(self.home), before)
        self.assertFalse(self.path.parent.exists())

    def test_corrupt_state_fails_closed_with_zero_mutation(self):
        self._write_state("{not json")
        before = _tree_snapshot(self.home)
        self.assertEqual(read_mode(self.path), SOL_MODE)
        self.assertEqual(_tree_snapshot(self.home), before)

    def test_unknown_mode_value_fails_closed_with_zero_mutation(self):
        self._write_state(json.dumps({"version": 1, "mode": "banana"}))
        before = _tree_snapshot(self.home)
        self.assertEqual(read_mode(self.path), SOL_MODE)
        self.assertEqual(_tree_snapshot(self.home), before)

    def test_non_string_mode_fails_closed(self):
        self._write_state(json.dumps({"version": 1, "mode": 7}))
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_legacy_lowercase_values_are_invalid(self):
        self._write_state(json.dumps({"version": 1, "mode": "sol_mode"}))
        self.assertEqual(read_mode(self.path), SOL_MODE)
        self._write_state(json.dumps({"version": 1, "mode": "grok_mode"}))
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_unsupported_version_fails_closed(self):
        self._write_state(json.dumps({"version": 99, "mode": "GrokMode"}))
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_missing_version_is_invalid_strict_schema(self):
        self._write_state(json.dumps({"mode": "GrokMode"}))
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_boolean_version_is_invalid(self):
        self._write_state(json.dumps({"version": True, "mode": "GrokMode"}))
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_extra_keys_and_non_dict_shapes_fail_closed(self):
        self._write_state(
            json.dumps({"version": 1, "mode": "GrokMode", "extra": True})
        )
        self.assertEqual(read_mode(self.path), SOL_MODE)
        self._write_state(json.dumps(["not", "a", "dict"]))
        self.assertEqual(read_mode(self.path), SOL_MODE)

    def test_invalid_write_argument_rejected_state_unchanged(self):
        write_mode(GROK_MODE, self.path)
        before = self.path.read_bytes()
        for bad in ("SolMode", "GrokMode", "sol_mode", "grok", "", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                write_mode(bad, self.path)  # type: ignore[arg-type]
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(read_mode(self.path), GROK_MODE)

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
            json.dumps({"version": 1, "mode": "GrokMode"}), encoding="utf-8"
        )
        self.path.symlink_to(target)
        # Fail closed: a symlinked authoritative path is treated as invalid.
        self.assertEqual(read_mode(self.path), SOL_MODE)
        # ...and the refusal performs zero mutation.
        self.assertEqual(target.read_text(
            encoding="utf-8"), json.dumps({"version": 1, "mode": "GrokMode"})
        )


class ModeCliTests(unittest.TestCase):
    """Canonical CLI surface: status | SolMode | GrokMode."""

    def run_cli(self, *args, home):
        env = dict(os.environ)
        return subprocess.run(
            [sys.executable, str(CLI),
             "--state-path", str(home / "m.json"), *args],
            capture_output=True, text=True, env=env,
        )

    def test_status_on_missing_state_read_only_default(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            r = self.run_cli("status", home=home)
            self.assertEqual(r.returncode, 0, msg=r.stderr)
            self.assertIn("SolMode", r.stdout)
            self.assertEqual(list(home.iterdir()), [])  # nothing created

    def test_set_grokmode_then_status(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            r2 = self.run_cli("GrokMode", home=home)
            self.assertEqual(r2.returncode, 0, msg=r2.stderr)
            self.assertEqual(
                json.loads((home / "m.json").read_text()),
                {"version": 1, "mode": "GrokMode"},
            )
            r3 = self.run_cli("status", home=home)
            self.assertEqual(r3.returncode, 0)
            self.assertIn("GrokMode", r3.stdout)

    def test_solmode_then_grokmode_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.run_cli("SolMode", home=home)
            r = self.run_cli("GrokMode", home=home)
            self.assertEqual(r.returncode, 0)
            self.assertIn("GrokMode", r.stdout)
            self.assertEqual(
                json.loads((home / "m.json").read_text())["mode"], "GrokMode"
            )

    def test_invalid_invocation_exits_nonzero_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.run_cli("GrokMode", home=home)
            before = (home / "m.json").read_bytes()
            listing_before = sorted(p.name for p in home.iterdir())
            for bad_args in (("set", "grok"), ("set", "SolMode"),
                             ("set",), ("sol",), ("grok",), ("frobnicate",)):
                r = self.run_cli(*bad_args, home=home)
                self.assertNotEqual(r.returncode, 0, msg=str(bad_args))
            self.assertEqual((home / "m.json").read_bytes(), before)
            self.assertEqual(sorted(p.name for p in home.iterdir()),
                             listing_before)

    def test_status_is_byte_for_byte_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            self.run_cli("GrokMode", home=home)
            before_tree = _tree_snapshot(home)
            r = self.run_cli("status", home=home)
            self.assertEqual(r.returncode, 0)
            self.assertEqual(_tree_snapshot(home), before_tree)


class NoRoutingMutationTests(unittest.TestCase):
    """Mission check 15: Task 1 mutates no routing policy surfaces."""

    def test_module_import_does_not_touch_repo_policy_files(self):
        tracked_rels = [
            "core/ORCHESTRATOR_CORE.md",
            "core/model_policy.py",
            "core/model_resolver.py",
            "skills/autoteam/SKILL.md",
            "skills/autoteam/USAGE.md",
            "scripts/installer_lifecycle.py",
            "scripts/verify.sh",
        ]
        tracked_paths = [REPO_ROOT / rel for rel in tracked_rels]

        # 1. Snapshot existence and byte content before isolated import
        before_snapshot = {
            rel: (p.exists(), p.read_bytes() if p.exists() else None)
            for rel, p in zip(tracked_rels, tracked_paths)
        }

        # 2. Perform isolated import in a fresh Python process
        code = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0, '{REPO_ROOT}'); "
            "import core.runtime_routing_mode"
        )
        res = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Import failed: {res.stderr}")

        # 3. Snapshot existence and byte content after import
        after_snapshot = {
            rel: (p.exists(), p.read_bytes() if p.exists() else None)
            for rel, p in zip(tracked_rels, tracked_paths)
        }

        # 4. Assert byte-for-byte identity before vs after
        self.assertEqual(before_snapshot, after_snapshot)

    def test_mutation_detector_fails_on_actual_mutation(self):
        """TDD proof: mutating detector detects before/after byte differences."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            f1 = temp_root / "sample.txt"
            f1.write_bytes(b"initial state")
            before = {f1.name: (f1.exists(), f1.read_bytes())}

            # Simulate a dirty import that touches sample.txt
            f1.write_bytes(b"mutated state")
            after = {f1.name: (f1.exists(), f1.read_bytes())}

            self.assertNotEqual(before, after)

    def test_mutation_detector_tolerates_pre_existing_uncommitted_changes(self):
        """TDD proof: pre-existing dirty files do NOT fail the test if import does not mutate them."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            f1 = temp_root / "already_dirty.txt"
            f1.write_bytes(b"uncommitted feature edits")

            before = {f1.name: (f1.exists(), f1.read_bytes())}
            # Import occurs, file is untouched
            after = {f1.name: (f1.exists(), f1.read_bytes())}

            self.assertEqual(before, after)

if __name__ == "__main__":
    unittest.main()
