"""Black-box RED tests for the installer/verify/uninstaller lifecycle.

Every test drives the shipped shell scripts against a disposable target home.
The manifest is the ownership boundary: a malformed, ambiguous, or escaping
manifest must fail closed before any payload or user file is changed.
"""

from __future__ import annotations

import hashlib
from unittest import mock
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
CORE_MODULES = (
    "model_availability",
    "model_capabilities",
    "model_discovery",
    "model_intelligence",
    "model_policy",
    "model_resolver",
)
DOCTOR_BIN = Path(".agents/bin/doctor")
CONFIGURE_BIN = Path(".agents/bin/configure-models")
MODELS_CONFIG = Path(".agents/config/models.yaml")


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

    def _write_v1_manifest(self, home: Path) -> dict:
        """Convert a fresh v2 fixture to the legacy installer manifest shape."""
        v2 = self._read_manifest(home)
        entries = self._entries(v2)
        v1 = {
            "version": 1,
            "installed_files": {
                key: {
                    "installed_sha256": info["sha256"],
                    "backup_path": None,
                }
                for key, info in entries.items()
            },
        }
        self._write_manifest(home, v1)
        return v1

    def _migrate(self, home: Path, *, dry_run: bool = False):
        args = ["--migrate-manifest-v1"]
        if dry_run:
            args.append("--dry-run")
        return subprocess.run(
            [str(INSTALL), *args, "--target-home", str(home)],
            cwd=DEV_ROOT,
            capture_output=True,
            text=True,
        )

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

    def test_clean_install_packages_model_policy_payload_and_unmanaged_config(self):
        with tempfile.TemporaryDirectory(prefix="installer-model-policy-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            manifest = self._read_manifest(home)
            entries = self._entries(manifest)
            managed_dests = {
                self._manifest_path_for_entry(home, manifest, key).resolve()
                for key in entries
            }

            for name in CORE_MODULES:
                dest = (home / ".agents" / "core" / f"{name}.py").resolve()
                self.assertTrue(dest.is_file(), f"missing core module: {dest}")
                self.assertIn(dest, managed_dests, f"core module not managed: {dest}")

            for rel in (DOCTOR_BIN, CONFIGURE_BIN):
                dest = (home / rel).resolve()
                self.assertTrue(dest.is_file(), f"missing command: {dest}")
                self.assertIn(dest, managed_dests, f"command not managed: {dest}")
                self.assertTrue(os.access(dest, os.X_OK), f"command not executable: {dest}")

            config = (home / MODELS_CONFIG).resolve()
            self.assertTrue(config.is_file(), "missing unmanaged models.yaml")
            self.assertNotIn(config, managed_dests, "models.yaml must not be managed")

    def test_installed_commands_execute_readonly(self):
        with tempfile.TemporaryDirectory(prefix="installer-readonly-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            config = home / MODELS_CONFIG
            env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

            doctor = subprocess.run(
                [str(home / DOCTOR_BIN), "--config", str(config), "--target-home", str(home)],
                cwd=DEV_ROOT,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(doctor.returncode, 0, self._message("doctor", doctor))

            configure = subprocess.run(
                [str(home / CONFIGURE_BIN), "--config", str(config)],
                cwd=DEV_ROOT,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(configure.returncode, 0, self._message("configure-models", configure))

    def test_existing_user_config_preserved_across_install_upgrade_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="installer-config-preserve-red-") as raw_home:
            home = Path(raw_home)
            config = home / MODELS_CONFIG
            config.parent.mkdir(parents=True, exist_ok=True)
            custom = b"# user-owned custom bytes\n"
            config.write_bytes(custom)

            self._install(home)
            self.assertEqual(config.read_bytes(), custom, "install overwrote user config")

            upgrade = self._run(INSTALL, home)
            self.assertEqual(upgrade.returncode, 0, self._message("upgrade", upgrade))
            self.assertEqual(config.read_bytes(), custom, "upgrade overwrote user config")

            self.assertTrue((home / ".agents" / "core" / "model_policy.py").is_file())
            self.assertTrue((home / DOCTOR_BIN).is_file())

            uninstall = self._run(UNINSTALL, home)
            self.assertEqual(uninstall.returncode, 0, self._message("uninstall", uninstall))
            self.assertTrue(config.is_file(), "uninstall removed user config")
            self.assertEqual(config.read_bytes(), custom, "uninstall changed user config")

            for name in CORE_MODULES:
                self.assertFalse(
                    (home / ".agents" / "core" / f"{name}.py").exists(),
                    f"core module {name} not removed",
                )
            self.assertFalse((home / DOCTOR_BIN).exists(), "doctor not removed")
            self.assertFalse((home / CONFIGURE_BIN).exists(), "configure-models not removed")

    def test_managed_cli_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="installer-cli-tamper-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            doctor = home / DOCTOR_BIN
            tampered = b"#!/usr/bin/env python3\nprint('tampered')\n"
            doctor.write_bytes(tampered)

            verify = self._run(VERIFY, home)
            self.assertNotEqual(
                verify.returncode, 0, self._message("verify accepted tampered CLI", verify)
            )

            uninstall = self._run(UNINSTALL, home)
            self.assertNotEqual(
                uninstall.returncode,
                0,
                self._message("uninstall removed tampered CLI", uninstall),
            )
            self.assertEqual(doctor.read_bytes(), tampered, "tampered CLI was mutated")

    def test_uninstall_removes_managed_modules_commands_but_preserves_default_config(self):
        with tempfile.TemporaryDirectory(prefix="installer-uninstall-model-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            config = home / MODELS_CONFIG
            original = config.read_bytes()
            self.assertTrue(original, "default config should be non-empty")

            result = self._run(UNINSTALL, home)
            self.assertEqual(result.returncode, 0, self._message("uninstall", result))

            self.assertTrue(config.is_file(), "default config removed by uninstall")
            self.assertEqual(config.read_bytes(), original, "default config changed by uninstall")

            for name in CORE_MODULES:
                self.assertFalse(
                    (home / ".agents" / "core" / f"{name}.py").exists(),
                    f"core module {name} not removed",
                )
            self.assertFalse((home / DOCTOR_BIN).exists(), "doctor not removed")
            self.assertFalse((home / CONFIGURE_BIN).exists(), "configure-models not removed")
            self.assertFalse(
                (home / ".agents" / "bin" / "mission-trace").exists(),
                "mission-trace not removed",
            )

    def test_migrate_v1_explicitly_claims_clean_files_repairs_missing_and_records_customizations(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            entries = v1["installed_files"]
            modified_key = next(
                key for key in entries if key.endswith("router-model-nine-router-stepplan-step-3-7-flash.toml")
            )
            missing_key = next(
                key for key in entries if key.endswith("router-model-custom-qwen3-8-27b.toml")
            )
            modified_path = Path(modified_key)
            modified_path.write_bytes(
                b"# user-owned router customization\n" + modified_path.read_bytes()
            )
            missing_path = Path(missing_key)
            missing_path.unlink()
            before_modified = modified_path.read_bytes()
            before = self._snapshot(home)

            dry_run = self._migrate(home, dry_run=True)
            self.assertEqual(dry_run.returncode, 0, self._message("migration dry-run", dry_run))
            self.assertEqual(self._snapshot(home), before)
            self.assertEqual(self._manifest_path(home).read_bytes(), json.dumps(v1, indent=2).encode() + b"\n")

            result = self._migrate(home)
            self.assertEqual(result.returncode, 0, self._message("migration", result))
            migrated = self._read_manifest(home)
            self.assertEqual(migrated.get("schema_version"), 2)
            managed = self._entries(migrated)
            omissions = migrated.get("migration_omissions")
            self.assertIsInstance(omissions, dict)
            modified_rel = str(modified_path.resolve().relative_to(home.resolve()))
            missing_rel = str(missing_path.resolve().relative_to(home.resolve()))
            self.assertIn(modified_rel, omissions)
            self.assertNotIn(missing_rel, omissions)
            self.assertNotIn(modified_key, managed)
            self.assertEqual(modified_path.read_bytes(), before_modified)
            self.assertEqual(missing_path.read_bytes(), (DEV_ROOT / "agents" / missing_path.name).read_bytes())
            self.assertEqual(omissions[modified_rel]["state"], "modified")
            self.assertEqual(
                omissions[modified_rel]["migration_sha256"],
                hashlib.sha256(before_modified).hexdigest(),
            )
            self.assertIn(missing_key, managed)
            verify = self._run(VERIFY, home)
            self.assertEqual(verify.returncode, 0, self._message("verify migrated omissions", verify))

    def test_v1_omitted_existing_unknown_payload_is_unknown_conflict_for_apply_and_dry_run(self):
        """An omitted v1 destination with unknown bytes must fail closed."""
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                with tempfile.TemporaryDirectory(prefix="installer-migrate-unknown-conflict-red-") as raw_home:
                    home = Path(raw_home)
                    self._install(home)
                    v1 = self._write_v1_manifest(home)
                    omitted_key = next(
                        key for key in v1["installed_files"] if key.endswith("ORCHESTRATOR_CORE.md")
                    )
                    destination = Path(omitted_key)
                    v1["installed_files"].pop(omitted_key)
                    destination.unlink()
                    unknown = b"unknown pre-existing bytes\n"
                    destination.write_bytes(unknown)
                    self._write_manifest(home, v1)
                    before_manifest = self._manifest_path(home).read_bytes()
                    before_snapshot = self._snapshot(home)

                    result = self._migrate(home, dry_run=dry_run)

                    self.assertNotEqual(result.returncode, 0, self._message("unknown conflict migration", result))
                    self.assertRegex(
                        f"{result.stdout}\n{result.stderr}",
                        r"(?i)unknown[ _-]*conflict|ambiguous",
                    )
                    self.assertEqual(destination.read_bytes(), unknown)
                    self.assertEqual(self._manifest_path(home).read_bytes(), before_manifest)
                    self.assertEqual(self._snapshot(home), before_snapshot)
                    self.assertFalse((home / ".multi-orchestrator-backups").exists())

    def test_v1_requires_explicit_migration_and_normal_lifecycle_is_unchanged(self):
        for script in (INSTALL, VERIFY, UNINSTALL):
            with self.subTest(script=script.name):
                with tempfile.TemporaryDirectory(prefix="installer-migrate-explicit-red-") as raw_home:
                    home = Path(raw_home)
                    self._install(home)
                    self._write_v1_manifest(home)
                    before = self._snapshot(home)
                    result = self._run(script, home)
                    self.assertNotEqual(result.returncode, 0, self._message(script.name, result))
                    self.assertEqual(self._snapshot(home), before)

    def test_migrated_omissions_are_persistent_and_unmanaged(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-persist-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            modified_key = next(
                key for key in v1["installed_files"] if key.endswith("router-model-nine-router-stepplan-step-3-7-flash.toml")
            )
            modified_path = Path(modified_key)
            modified_path.write_bytes(
                modified_path.read_bytes() + b"\n# user customization survives lifecycle\n"
            )
            self.assertEqual(self._migrate(home).returncode, 0)

            modified_path.write_bytes(
                modified_path.read_bytes() + b"# changed after migration\n"
            )
            preserved = modified_path.read_bytes()
            verify = self._run(VERIFY, home)
            self.assertEqual(verify.returncode, 0, self._message("verify omission", verify))
            install = self._run(INSTALL, home)
            self.assertEqual(install.returncode, 0, self._message("install omission", install))
            self.assertEqual(modified_path.read_bytes(), preserved)
            uninstall = self._run(UNINSTALL, home)
            self.assertEqual(uninstall.returncode, 0, self._message("uninstall omission", uninstall))
            self.assertEqual(modified_path.read_bytes(), preserved)

    def test_failed_or_repeated_v1_migration_does_not_mutate_fixture(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-atomic-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            before = self._snapshot(home)
            invalid = self._read_manifest(home)
            invalid["installed_files"]["../escape"] = {
                "installed_sha256": hashlib.sha256(b"escape").hexdigest(),
                "backup_path": None,
            }
            self._write_manifest(home, invalid)
            invalid_before = self._snapshot(home)
            failed = self._migrate(home)
            self.assertNotEqual(failed.returncode, 0, self._message("invalid migration", failed))
            self.assertEqual(self._snapshot(home), invalid_before)

            self._write_manifest(home, v1)
            migrated = self._migrate(home)
            self.assertEqual(migrated.returncode, 0, self._message("migration", migrated))
            after_first = self._snapshot(home)
            repeated = self._migrate(home)
            self.assertNotEqual(repeated.returncode, 0, self._message("repeated migration", repeated))
            self.assertEqual(self._snapshot(home), after_first)
            self.assertNotEqual(before, after_first)

    def test_migration_fixture_preserves_5_custom_agents_repairs_2_missing_and_claims_1_pristine(self):
        """The bounded migration classifies the explicit 8-agent legacy set once."""
        with tempfile.TemporaryDirectory(prefix="installer-migrate-8-5-2-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            # The shipped declarations are target-home absolute paths; select
            # only the eight relevant legacy agent declarations explicitly.
            agent_entries = [
                key for key in v1["installed_files"] if "/.codex/agents/" in key and key.endswith(".toml")
            ]
            self.assertEqual(len(agent_entries), 8)
            custom = agent_entries[:5]
            missing = agent_entries[5:7]
            pristine = agent_entries[7]
            before_custom = {}
            for index, key in enumerate(custom):
                path = Path(key)
                before_custom[key] = (f"# custom declaration {index}\n" + path.read_text(encoding="utf-8")).encode()
                path.write_bytes(before_custom[key])
            for key in missing:
                Path(key).unlink()
            self._write_manifest(home, v1)

            result = self._migrate(home)
            self.assertEqual(result.returncode, 0, self._message("migration", result))
            migrated = self._read_manifest(home)
            managed = self._entries(migrated)
            provenance = migrated.get("migration_provenance")
            self.assertIsInstance(provenance, dict)
            self.assertEqual(provenance.get("from_schema_version"), 1)
            classifications = provenance.get("classifications")
            self.assertIsInstance(classifications, dict)
            self.assertEqual(len(classifications), len(v1["installed_files"]))

            for key, original in before_custom.items():
                self.assertEqual(Path(key).read_bytes(), original)
                self.assertNotIn(key, managed)
                self.assertEqual(classifications[key], "preserved_customized")
            for key in missing:
                path = Path(key)
                self.assertTrue(path.is_file(), f"missing legacy declaration not restored: {path}")
                self.assertEqual(
                    path.read_bytes(),
                    (DEV_ROOT / "agents" / path.name).read_bytes(),
                )
                self.assertIn(key, managed)
                self.assertEqual(classifications[key], "repaired_missing")
            self.assertIn(pristine, managed)
            self.assertEqual(classifications[pristine], "pristine")

    def test_modified_non_agent_payload_blocks_migration_before_any_mutation(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-core-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            core_key = next(key for key in v1["installed_files"] if key.endswith("ORCHESTRATOR_CORE.md"))
            core = Path(core_key)
            core.write_bytes(b"user changed core\n")
            self._write_manifest(home, v1)
            before = self._snapshot(home)
            result = self._migrate(home)
            self.assertNotEqual(result.returncode, 0, self._message("unsafe core migration", result))
            self.assertEqual(self._snapshot(home), before)
            self.assertEqual(self._read_manifest(home).get("version"), 1)

    def test_migration_preserves_validated_legacy_backup_for_future_uninstall(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-backup-red-") as raw_home:
            home = Path(raw_home)
            original = b"pre-v1 user core bytes\n"
            destination = home / ".agents" / "orchestrator-shared" / "ORCHESTRATOR_CORE.md"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(original)
            self._install(home)
            v2 = self._read_manifest(home)
            key, info, _ = self._first_entry(home, v2)
            # Move the proven v1 backup into a legacy target-home location and
            # retain only its byte hash in the v1 manifest.
            backup = Path(info["backup_path"])
            legacy_backup = home / "legacy-v1-backups" / "core.bak"
            legacy_backup.parent.mkdir(parents=True, exist_ok=True)
            legacy_backup.write_bytes(backup.read_bytes())
            backup.unlink()
            v1 = {
                "version": 1,
                "installed_files": {
                    key: (
                        {
                            "installed_sha256": info["sha256"],
                            "backup_path": str(legacy_backup),
                            "backup_sha256": hashlib.sha256(original).hexdigest(),
                        }
                        if Path(key).resolve() == destination.resolve()
                        else {
                            "installed_sha256": info["sha256"],
                            "backup_path": None,
                        }
                    )
                    for key, info in self._entries(v2).items()
                },
            }
            self._write_manifest(home, v1)
            self.assertEqual(self._migrate(home).returncode, 0)
            migrated = self._read_manifest(home)
            migrated_info = migrated["installed_files"][key]
            relocated = migrated_info.get("backup_path")
            self.assertIsNotNone(relocated)
            self.assertTrue(
                    Path(relocated).resolve().is_relative_to(
                    (home / ".multi-orchestrator-backups").resolve()
                )
            )
            self.assertEqual(Path(relocated).read_bytes(), original)
            self.assertEqual(self._run(UNINSTALL, home).returncode, 0)
            self.assertEqual(destination.read_bytes(), original)

    def test_migration_dry_run_is_byte_identical_with_repairs_planned(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-dry-run-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            missing_key = next(key for key in v1["installed_files"] if "/.codex/agents/" in key)
            Path(missing_key).unlink()
            self._write_manifest(home, v1)
            before = self._snapshot(home)
            result = self._migrate(home, dry_run=True)
            self.assertEqual(result.returncode, 0, self._message("migration dry-run", result))
            self.assertEqual(self._snapshot(home), before)
            self.assertEqual(self._read_manifest(home).get("version"), 1)
            self.assertIn("repaired_missing", result.stdout)

    def test_controlled_copy_failure_rolls_back_exact_v1_manifest_and_payload(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-rollback-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            missing_key = next(key for key in v1["installed_files"] if "/.codex/agents/" in key)
            Path(missing_key).unlink()
            self._write_manifest(home, v1)
            manifest_before = self._manifest_path(home).read_bytes()
            snapshot_before = self._snapshot(home)

            from scripts import installer_lifecycle

            real_copy2 = installer_lifecycle.shutil.copy2
            calls = {"count": 0}

            def fail_on_second_copy(source, destination, *args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise OSError("synthetic controlled copy failure")
                return real_copy2(source, destination, *args, **kwargs)

            with mock.patch.object(installer_lifecycle.shutil, "copy2", fail_on_second_copy):
                with self.assertRaises(OSError):
                    installer_lifecycle.cmd_migrate_manifest_v1(
                        str(DEV_ROOT),
                        str(home),
                        str(self._manifest_path(home)),
                        False,
                    )
            self.assertEqual(self._manifest_path(home).read_bytes(), manifest_before)
            self.assertEqual(self._snapshot(home), snapshot_before)

    def test_migration_provenance_is_schema_validated_by_all_lifecycle_commands(self):
        with tempfile.TemporaryDirectory(prefix="installer-migrate-provenance-red-") as raw_home:
            home = Path(raw_home)
            self._install(home)
            v1 = self._write_v1_manifest(home)
            custom_key = next(key for key in v1["installed_files"] if "/.codex/agents/" in key)
            Path(custom_key).write_bytes(b"# valid custom declaration marker\n" + Path(custom_key).read_bytes())
            self._write_manifest(home, v1)
            self.assertEqual(self._migrate(home).returncode, 0)
            manifest = self._read_manifest(home)
            manifest["migration_provenance"]["classifications"].pop(custom_key)
            self._write_manifest(home, manifest)
            before = self._snapshot(home)
            for script in (INSTALL, VERIFY, UNINSTALL):
                with self.subTest(script=script.name):
                    result = self._run(script, home)
                    self.assertNotEqual(result.returncode, 0, self._message(script.name, result))
                    self.assertEqual(self._snapshot(home), before)

    def test_migration_rejects_unknown_or_reserved_legacy_paths_before_mutation(self):
        for kind in ("unknown", "reserved"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory(prefix="installer-migrate-conflict-red-") as raw_home:
                    home = Path(raw_home)
                    self._install(home)
                    v1 = self._write_v1_manifest(home)
                    source_info = next(iter(v1["installed_files"].values()))
                    if kind == "unknown":
                        conflict = home / ".codex" / "agents" / "not-shipped.toml"
                        v1["installed_files"][str(conflict)] = {
                            "installed_sha256": source_info["installed_sha256"],
                            "backup_path": None,
                        }
                    else:
                        reserved = home / ".agents" / "config" / "models.yaml"
                        v1["installed_files"][next(iter(v1["installed_files"]))]["backup_path"] = str(reserved)
                    self._write_manifest(home, v1)
                    before = self._snapshot(home)
                    result = self._migrate(home)
                    self.assertNotEqual(result.returncode, 0, self._message("unsafe migration", result))
                    self.assertEqual(self._snapshot(home), before)


if __name__ == "__main__":
    unittest.main()
