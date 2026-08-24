"""Black-box RED tests for the installer/verify/uninstaller lifecycle.

Every test drives the shipped shell scripts against a disposable target home.
The manifest is the ownership boundary: a malformed, ambiguous, or escaping
manifest must fail closed before any payload or user file is changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


DEV_ROOT = Path(__file__).resolve().parents[1]
INSTALL = DEV_ROOT / "scripts" / "install.sh"
VERIFY = DEV_ROOT / "scripts" / "verify.sh"
UNINSTALL = DEV_ROOT / "scripts" / "uninstall.sh"
MANIFEST_REL = Path(".agents/.multi-orchestrator-install-manifest.json")


class InstallerLifecycleTests(unittest.TestCase):
    """Exercise real lifecycle scripts without touching the active home."""

    def _run(self, script: Path, home: Path, *, cwd: Path | None = None):
        return subprocess.run(
            [str(script), "--target-home", str(home)],
            cwd=cwd or DEV_ROOT,
            capture_output=True,
            text=True,
        )

    def _message(self, label: str, result: subprocess.CompletedProcess[str]) -> str:
        return (
            f"{label} exited {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def _install(self, home: Path):
        result = self._run(INSTALL, home)
        self.assertEqual(result.returncode, 0, self._message("install", result))
        return result

    def _manifest_path(self, home: Path) -> Path:
        return home / MANIFEST_REL

    def _read_manifest(self, home: Path) -> dict:
        path = self._manifest_path(home)
        self.assertTrue(path.is_file(), f"manifest missing: {path}")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            self.fail(f"manifest is not JSON: {exc}")
        self.assertIsInstance(value, dict, "manifest root must be an object")
        return value

    def _entries(self, manifest: dict) -> dict:
        """Return the manifest file map while keeping the historical key name."""
        entries = manifest.get("installed_files", manifest.get("files"))
        self.assertIsInstance(entries, dict, "manifest file ownership map must be an object")
        self.assertTrue(entries, "manifest must track at least one installed file")
        return entries

    def _manifest_path_for_entry(self, home: Path, manifest: dict, key: str) -> Path:
        # Malformed-manifest tests deliberately exercise a missing root.  The
        # fallback keeps fixture setup executable; the scripts must still
        # reject that manifest before touching any files.
        managed_root = manifest.get("managed_root", str(home))
        self.assertIsInstance(managed_root, str, "manifest managed_root must be a path")
        root = Path(managed_root)
        if not root.is_absolute():
            root = home / root
        path = Path(key)
        return path if path.is_absolute() else root / path

    def _first_entry(self, home: Path, manifest: dict) -> tuple[str, dict, Path]:
        key, info = next(iter(self._entries(manifest).items()))
        self.assertIsInstance(key, str, "manifest file path must be a string")
        self.assertIsInstance(info, dict, "manifest file ownership entry must be an object")
        return key, info, self._manifest_path_for_entry(home, manifest, key)

    def _snapshot(self, root: Path) -> dict[str, tuple[str, int]]:
        """Hash regular files and record symlinks so mutation is observable."""
        result: dict[str, tuple[str, int]] = {}
        if not root.exists():
            return result
        for path in sorted(root.rglob("*")):
            rel = str(path.relative_to(root))
            if path.is_symlink():
                result[rel] = (f"symlink:{os.readlink(path)}", 0)
            elif path.is_file():
                data = path.read_bytes()
                result[rel] = (hashlib.sha256(data).hexdigest(), len(data))
        return result

    def _write_manifest(self, home: Path, manifest: dict) -> None:
        path = self._manifest_path(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    def _schema_case(self, mutate):
        """All lifecycle entry points reject the same malformed manifest pre-write."""
        for script in (INSTALL, VERIFY, UNINSTALL):
            with self.subTest(script=script.name):
                with tempfile.TemporaryDirectory(prefix="installer-schema-red-") as raw_home:
                    home = Path(raw_home)
                    self._install(home)
                    manifest_path = self._manifest_path(home)
                    manifest = self._read_manifest(home)
                    mutate(manifest)
                    self._write_manifest(home, manifest)
                    before = self._snapshot(home)

                    result = self._run(script, home)
                    self.assertNotEqual(
                        result.returncode,
                        0,
                        self._message(f"{script.name} accepted malformed manifest", result),
                    )
                    after = self._snapshot(home)
                    self.assertEqual(
                        after,
                        before,
                        self._message(
                            f"{script.name} mutated target after malformed manifest", result
                        ),
                    )
                    self.assertTrue(manifest_path.is_file(), "failed validation removed manifest")

    def _path_case(self, mutate, sentinel_for_home, *, cwd_mode: str = "repo"):
        """Containment failures must not touch target files or an escaped sentinel."""
        for script in (INSTALL, VERIFY, UNINSTALL):
            with self.subTest(script=script.name):
                with tempfile.TemporaryDirectory(prefix="installer-path-red-") as raw_home:
                    home = Path(raw_home)
                    self._install(home)
                    manifest = self._read_manifest(home)
                    mutate(home, manifest)
                    self._write_manifest(home, manifest)
                    sentinel = sentinel_for_home(home)
                    sentinel.parent.mkdir(parents=True, exist_ok=True)
                    sentinel.write_text("user sentinel\n", encoding="utf-8")
                    before_home = self._snapshot(home)
                    before_sentinel = sentinel.read_bytes()
                    cwd = home if cwd_mode == "home" else DEV_ROOT

                    result = self._run(script, home, cwd=cwd)
                    self.assertNotEqual(
                        result.returncode,
                        0,
                        self._message(f"{script.name} accepted escaping manifest path", result),
                    )
                    self.assertEqual(self._snapshot(home), before_home)
                    self.assertEqual(sentinel.read_bytes(), before_sentinel)

    def test_clean_install_writes_payload_manifest_and_ownership_metadata(self):
        """A clean install emits a bounded manifest with owned payload files."""
        with tempfile.TemporaryDirectory(prefix="installer-clean-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            manifest = self._read_manifest(home)

            self.assertIsInstance(manifest.get("installer_id"), str)
            self.assertTrue(manifest["installer_id"])
            self.assertIsInstance(manifest.get("managed_root"), str)
            managed_root = Path(manifest["managed_root"])
            if not managed_root.is_absolute():
                managed_root = home / managed_root
            self.assertEqual(managed_root.resolve(), home.resolve())

            entries = self._entries(manifest)
            for key, info in entries.items():
                self.assertIsInstance(info, dict)
                self.assertEqual(info.get("ownership"), "managed")
                destination = self._manifest_path_for_entry(home, manifest, key)
                self.assertTrue(destination.is_file(), f"managed payload missing: {destination}")
                self.assertEqual(
                    destination.resolve().is_relative_to(managed_root.resolve()),
                    True,
                    f"manifest path escapes managed_root: {destination}",
                )
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
                self.assertIn(digest, {info.get("sha256"), info.get("installed_sha256")})

    def test_missing_installer_id_fails_closed_before_mutation(self):
        def mutate(manifest):
            manifest.pop("installer_id", None)

        self._schema_case(mutate)

    def test_missing_managed_root_fails_closed_before_mutation(self):
        def mutate(manifest):
            manifest.pop("managed_root", None)

        self._schema_case(mutate)

    def test_missing_file_ownership_fails_closed_before_mutation(self):
        def mutate(manifest):
            _, info = next(iter(self._entries(manifest).items()))
            info.pop("ownership", None)

        self._schema_case(mutate)

    def test_malformed_manifest_structure_fails_closed_before_mutation(self):
        def mutate(manifest):
            manifest["installed_files"] = []
            manifest["files"] = []

        self._schema_case(mutate)

    def test_absolute_external_manifest_path_fails_closed_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix="installer-external-red-") as raw_parent:
            parent = Path(raw_parent)
            sentinel = parent / "external-sentinel.txt"

            def mutate(home, manifest):
                entries = self._entries(manifest)
                _, info = next(iter(entries.items()))
                info = dict(info)
                info.setdefault("ownership", "managed")
                info["sha256"] = hashlib.sha256(b"user sentinel\n").hexdigest()
                entries[str(sentinel)] = info

            self._path_case(mutate, lambda _home: sentinel)

    def test_parent_traversal_manifest_path_fails_closed_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix="installer-traversal-red-") as raw_home:
            home = Path(raw_home)
            sentinel = home.parent / "escape-sentinel.txt"

            def mutate(_home, manifest):
                entries = self._entries(manifest)
                _, info = next(iter(entries.items()))
                escaped = dict(info)
                escaped.setdefault("ownership", "managed")
                escaped["sha256"] = hashlib.sha256(b"user sentinel\n").hexdigest()
                entries["../escape-sentinel.txt"] = escaped

            self._path_case(mutate, lambda home: home.parent / "escape-sentinel.txt", cwd_mode="home")

    def test_path_outside_declared_managed_root_fails_closed_without_mutation(self):
        with tempfile.TemporaryDirectory(prefix="installer-root-red-") as raw_home:
            def mutate(home, manifest):
                manifest["managed_root"] = str(home / ".agents")
                entries = self._entries(manifest)
                _, info = next(iter(entries.items()))
                escaped = dict(info)
                escaped.setdefault("ownership", "managed")
                escaped["sha256"] = hashlib.sha256(b"user sentinel\n").hexdigest()
                entries[str(home / "outside-managed-root.txt")] = escaped

            self._path_case(mutate, lambda home: home / "outside-managed-root.txt")

    def test_unchanged_managed_payload_is_accepted_by_verify(self):
        with tempfile.TemporaryDirectory(prefix="installer-ownership-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            result = self._run(VERIFY, home)
            self.assertEqual(result.returncode, 0, self._message("verify", result))

    def test_modified_managed_file_is_detected_and_never_overwritten_or_deleted(self):
        with tempfile.TemporaryDirectory(prefix="installer-modified-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            manifest = self._read_manifest(home)
            _, _, destination = self._first_entry(home, manifest)
            modified = b"user-owned modification\n"
            destination.write_bytes(modified)

            verify = self._run(VERIFY, home)
            self.assertNotEqual(verify.returncode, 0, self._message("verify accepted modified file", verify))

            upgrade = self._run(INSTALL, home)
            self.assertEqual(
                destination.read_bytes(),
                modified,
                self._message("install overwrote modified managed file", upgrade),
            )

            uninstall = self._run(UNINSTALL, home)
            self.assertEqual(
                destination.read_bytes(),
                modified,
                self._message("uninstall deleted modified managed file", uninstall),
            )

    def test_upgrade_removes_retired_owned_file_but_leaves_unknown_user_file(self):
        with tempfile.TemporaryDirectory(prefix="installer-upgrade-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            manifest_a = self._read_manifest(home)
            entries_a = self._entries(manifest_a)
            _, source_info = next(iter(entries_a.items()))
            retired = home / ".agents" / "orchestrator-shared" / "retired-from-a.txt"
            retired.parent.mkdir(parents=True, exist_ok=True)
            retired.write_text("retired package payload\n", encoding="utf-8")
            retired_info = dict(source_info)
            retired_info["ownership"] = "managed"
            retired_info["sha256"] = hashlib.sha256(retired.read_bytes()).hexdigest()
            retired_info["installed_sha256"] = retired_info["sha256"]
            entries_a[str(retired)] = retired_info
            user_file = home / ".agents" / "orchestrator-shared" / "user-owned.txt"
            user_file.write_text("keep me\n", encoding="utf-8")
            self._write_manifest(home, manifest_a)
            manifest_a_bytes = self._manifest_path(home).read_bytes()

            upgrade = self._run(INSTALL, home)
            self.assertEqual(upgrade.returncode, 0, self._message("upgrade", upgrade))
            manifest_b = self._read_manifest(home)
            self.assertNotEqual(self._manifest_path(home).read_bytes(), manifest_a_bytes)
            self.assertFalse(retired.exists(), "retired package-owned file was not removed")
            self.assertNotIn(str(retired), self._entries(manifest_b))
            self.assertEqual(user_file.read_text(encoding="utf-8"), "keep me\n")

    def test_uninstall_restores_preexisting_owned_destination_and_preserves_unrelated_file(self):
        with tempfile.TemporaryDirectory(prefix="installer-uninstall-red-") as raw_home:
            home = Path(raw_home)
            preexisting = home / ".agents" / "orchestrator-shared" / "ORCHESTRATOR_CORE.md"
            preexisting.parent.mkdir(parents=True, exist_ok=True)
            preexisting.write_text("user baseline\n", encoding="utf-8")
            unrelated = home / ".agents" / "user-not-managed.txt"
            unrelated.write_text("keep me\n", encoding="utf-8")
            self._install(home)
            result = self._run(UNINSTALL, home)
            self.assertEqual(result.returncode, 0, self._message("uninstall", result))
            self.assertEqual(preexisting.read_text(encoding="utf-8"), "user baseline\n")
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep me\n")
            self.assertFalse(self._manifest_path(home).exists())

    def test_uninstall_corrupt_manifest_fails_closed_and_preserves_payload(self):
        with tempfile.TemporaryDirectory(prefix="installer-corrupt-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            manifest_path = self._manifest_path(home)
            before = self._snapshot(home)
            manifest_path.write_text("{ definitely not json\n", encoding="utf-8")
            expected_after_corruption = self._snapshot(home)

            result = self._run(UNINSTALL, home)
            self.assertNotEqual(result.returncode, 0, self._message("uninstall accepted corrupt manifest", result))
            self.assertTrue(manifest_path.exists())
            after = self._snapshot(home)
            self.assertEqual(
                after,
                expected_after_corruption,
                self._message("uninstall mutated payload after corrupt manifest", result),
            )
            self.assertNotEqual(before, after, "corrupting manifest should be observable")


if __name__ == "__main__":
    unittest.main()
