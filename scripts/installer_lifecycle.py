#!/usr/bin/env python3
"""Centralized installer lifecycle helper (Python standard library only).

This module is the single ownership boundary for install/verify/uninstall.  The
shell wrappers delegate manifest parsing, v2 schema validation, path
normalization, managed-root containment, ownership/hash checks, backup
metadata, and mutation planning here so malformed, ambiguous, or escaping
manifests fail closed before any payload or user file is changed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path


INSTALLER_ID = "multi-orchestrator"
SCHEMA_VERSION = 2
MANIFEST_REL = ".agents/.multi-orchestrator-install-manifest.json"
BACKUP_ROOT_REL = ".multi-orchestrator-backups"
# Target-home-relative paths the installer copies as unmanaged example
# profiles or user-owned config.  They must never become a managed destination
# or backup source, and are preserved across upgrade/uninstall.
RESERVED_UNMANAGED_RELS = (
    ".codex/sol-luna.config.toml",
    ".codex/grok-v2.config.toml",
    ".agents/config/models.yaml",
)

# (repo-relative source, target-home-relative destination)
PAYLOAD = [
    ("core/ORCHESTRATOR_CORE.md", ".agents/orchestrator-shared/ORCHESTRATOR_CORE.md"),
    ("skills/sol-luna-orchestrator-v2/SKILL.md", ".agents/skills/sol-luna-orchestrator-v2/SKILL.md"),
    ("skills/sol-luna-orchestrator-v2/USAGE.md", ".agents/skills/sol-luna-orchestrator-v2/USAGE.md"),
    ("skills/sol-luna-orchestrator-v2/agents/openai.yaml", ".agents/skills/sol-luna-orchestrator-v2/agents/openai.yaml"),
    ("skills/grok-orchestrator-v2/SKILL.md", ".agents/skills/grok-orchestrator-v2/SKILL.md"),
    ("skills/grok-orchestrator-v2/USAGE.md", ".agents/skills/grok-orchestrator-v2/USAGE.md"),
    ("skills/grok-orchestrator-v2/agents/openai.yaml", ".agents/skills/grok-orchestrator-v2/agents/openai.yaml"),
    ("scripts/mission-trace.py", ".agents/bin/mission-trace"),
    ("core/model_availability.py", ".agents/core/model_availability.py"),
    ("core/model_capabilities.py", ".agents/core/model_capabilities.py"),
    ("core/model_discovery.py", ".agents/core/model_discovery.py"),
    ("core/model_intelligence.py", ".agents/core/model_intelligence.py"),
    ("core/model_policy.py", ".agents/core/model_policy.py"),
    ("core/model_resolver.py", ".agents/core/model_resolver.py"),
    ("scripts/doctor.py", ".agents/bin/doctor"),
    ("scripts/configure_models.py", ".agents/bin/configure-models"),
]

# Managed payload destinations that must be executable on disk.
EXECUTABLE_PAYLOAD_NAMES = ("mission-trace", "doctor", "configure-models")

_SHA_RE = re.compile(r"^[0-9a-fA-F]{64}$")
MIGRATION_OMISSION_STATES = frozenset(("modified", "missing"))


class ManifestError(Exception):
    """Raised when a manifest is malformed, ambiguous, or escaping."""


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_symlink_path(root: Path, raw: Path, label: str) -> None:
    """Fail closed when any component under root traverses a symlink."""
    normalized = Path(os.path.normpath(str(raw)))
    try:
        rel = normalized.relative_to(root)
    except ValueError:
        return
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ManifestError(f"{label} traverses symlink: {current}")


def _resolve_within(root: Path, value: str, label: str) -> Path:
    raw = Path(value)
    if not raw.is_absolute():
        raw = root / raw
    _reject_symlink_path(root, raw, label)
    resolved = raw.resolve()
    if not resolved.is_relative_to(root):
        raise ManifestError(f"{label} escapes managed root: {value}")
    return resolved


def _resolve_manifest_path(target_home: str, manifest_path: str) -> Path:
    target = Path(target_home).resolve()
    raw = Path(manifest_path)
    if not raw.is_absolute():
        raw = target / raw
    _reject_symlink_path(target, raw, "manifest path")
    resolved = raw.resolve()
    if not resolved.is_relative_to(target):
        raise ManifestError(f"manifest path escapes target home: {manifest_path}")
    return resolved


def _package_backup_root(managed_root: Path) -> Path:
    """Return the canonical, package-owned backup directory under managed_root.

    The location is derived from the validated managed root and never from a
    manifest-supplied field, so a hostile manifest cannot redirect a backup
    onto a preserved profile or an arbitrary user path.
    """
    raw = managed_root / BACKUP_ROOT_REL
    _reject_symlink_path(managed_root, raw, "package backup root")
    resolved = raw.resolve()
    if resolved == managed_root or not resolved.is_relative_to(managed_root):
        raise ManifestError("package backup root escapes managed root")
    return resolved


def read_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"failed to read manifest {path}: {exc}")


def _validate_mutation_graph(
    target: Path, root: Path, normalized: dict, manifest_path: str
) -> None:
    """Reject canonical aliases that let one lifecycle mutation consume another.

    Every planned file operation is either a managed destination, a backup
    source, or the manifest.  Comparing canonical paths here fails closed
    before any payload or user file is touched.
    """
    dest_set = set(normalized.keys())
    backups = {
        info["backup_path"]
        for info in normalized.values()
        if info.get("backup_path") is not None
    }
    manifest_canon = str(Path(manifest_path).resolve())
    root_canon = str(root)
    backup_root = _package_backup_root(root)
    backup_root_canon = str(backup_root)
    reserved = {str((target / rel).resolve()) for rel in RESERVED_UNMANAGED_RELS}

    for dest in dest_set:
        if dest in reserved:
            raise ManifestError(f"managed destination is a reserved config profile: {dest}")
        dest_path = Path(dest)
        if dest_path == backup_root or dest_path.is_relative_to(backup_root):
            raise ManifestError(
                f"managed destination overlaps package backup root: {dest}"
            )

    for info in normalized.values():
        backup = info.get("backup_path")
        if backup is None:
            continue
        backup_path = Path(backup)
        for profile in reserved:
            if backup == profile or backup_path.is_relative_to(Path(profile)):
                raise ManifestError(
                    f"backup_path overlaps reserved config profile: {backup}"
                )
        if backup == backup_root_canon or not backup_path.is_relative_to(backup_root):
            raise ManifestError(f"backup_path escapes package backup root: {backup}")
        if backup in dest_set:
            raise ManifestError(f"backup_path collides with managed destination: {backup}")
        if backup == manifest_canon:
            raise ManifestError(f"backup_path collides with manifest: {backup}")
        if backup == root_canon:
            raise ManifestError(f"backup_path collides with managed root: {backup}")

    backup_owners = {}
    for dest, info in normalized.items():
        backup = info.get("backup_path")
        if backup is None:
            continue
        if backup in backup_owners:
            raise ManifestError(
                f"backup_path collision: {backup_owners[backup]!r} and {dest!r} "
                f"share canonical backup {backup}"
            )
        backup_owners[backup] = dest

    if manifest_canon in dest_set:
        raise ManifestError(f"managed destination collides with manifest: {manifest_canon}")
    if root_canon in dest_set:
        raise ManifestError(f"managed destination collides with managed root: {root_canon}")

    roles = sorted(dest_set | backups | {manifest_canon})
    for idx, a_str in enumerate(roles):
        a = Path(a_str)
        for b_str in roles[idx + 1:]:
            b = Path(b_str)
            if b.is_relative_to(a) or a.is_relative_to(b):
                raise ManifestError(
                    f"mutation-path ancestor/descendant conflict: {a} <-> {b}"
                )


def _validate_migration_omissions(
    target: Path,
    root: Path,
    installed: dict,
    omissions,
    manifest_path: str,
) -> dict:
    """Validate and canonicalize unmanaged paths preserved during v1 migration."""
    if omissions is None:
        return {}
    if not isinstance(omissions, dict):
        raise ManifestError("migration_omissions must be an object")

    installed_relative = {
        str(Path(dest).relative_to(target))
        for dest in installed
    }
    normalized = {}
    manifest_canon = Path(manifest_path).resolve()
    for key, info in omissions.items():
        if not isinstance(key, str) or not key:
            raise ManifestError("migration omission paths must be non-empty strings")
        relative = Path(key)
        if relative.is_absolute() or any(part in ("", ".", "..") for part in relative.parts):
            raise ManifestError(f"migration omission path must be canonical relative: {key}")
        if str(relative) != key:
            raise ManifestError(f"migration omission path must be normalized: {key}")
        dest = _resolve_within(target, key, "migration omission path")
        if not dest.is_relative_to(root):
            raise ManifestError(f"migration omission path escapes managed root: {key}")
        if dest == manifest_canon:
            raise ManifestError(f"migration omission path collides with manifest: {key}")
        if dest.is_symlink():
            raise ManifestError(f"migration omission path is a symlink: {key}")
        canonical = str(dest)
        canonical_relative = str(dest.relative_to(target))
        if canonical_relative != key:
            raise ManifestError(f"migration omission path is not target-relative: {key}")
        if key in installed_relative:
            raise ManifestError(f"migration omission overlaps installed file: {key}")
        if not isinstance(info, dict):
            raise ManifestError(f"migration omission entry must be an object: {key}")
        if info.get("ownership") != "unmanaged":
            raise ManifestError(f"migration omission ownership must be unmanaged: {key}")
        state = info.get("state")
        if state not in MIGRATION_OMISSION_STATES:
            raise ManifestError(f"invalid migration omission state for {key}")
        legacy_sha = info.get("legacy_sha256")
        if not isinstance(legacy_sha, str) or not _SHA_RE.match(legacy_sha):
            raise ManifestError(f"invalid legacy_sha256 for migration omission: {key}")
        migration_sha = info.get("migration_sha256")
        if state == "modified":
            if not isinstance(migration_sha, str) or not _SHA_RE.match(migration_sha):
                raise ManifestError(f"invalid migration_sha256 for modified omission: {key}")
        elif migration_sha is not None:
            raise ManifestError(f"missing omission cannot carry migration_sha256: {key}")
        normalized[canonical_relative] = {
            "ownership": "unmanaged",
            "state": state,
            "legacy_sha256": legacy_sha,
            "migration_sha256": migration_sha,
        }
    return normalized


def _validate_v2_manifest(manifest, target_home: str, manifest_path: str):
    """Return (managed_root, normalized_entries, normalized_omissions)."""
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("unsupported manifest schema_version")

    installer_id = manifest.get("installer_id")
    if installer_id != INSTALLER_ID:
        raise ManifestError(f"manifest installer_id must be {INSTALLER_ID!r}")

    raw_root = manifest.get("managed_root")
    if not isinstance(raw_root, str) or not raw_root.strip():
        raise ManifestError("manifest missing managed_root")

    target = Path(target_home).resolve()
    root = Path(raw_root)
    if not root.is_absolute():
        root = target / root
    root = root.resolve()
    if not root.is_relative_to(target):
        raise ManifestError("managed_root escapes target home")

    installed = manifest.get("installed_files")
    if not isinstance(installed, dict) or not installed:
        raise ManifestError("installed_files must be a non-empty object")

    normalized = {}
    source_keys = {}
    for key, info in installed.items():
        if not isinstance(key, str) or not isinstance(info, dict):
            raise ManifestError("installed_files entries must map string to object")
        dest = _resolve_within(root, key, "installed file path")
        if info.get("ownership") != "managed":
            raise ManifestError(f"non-managed ownership for {key}")
        sha = info.get("sha256", info.get("installed_sha256"))
        if not isinstance(sha, str) or not _SHA_RE.match(sha):
            raise ManifestError(f"invalid sha256 for {key}")
        info = dict(info)
        backup = info.get("backup_path")
        if backup is not None:
            if not isinstance(backup, str):
                raise ManifestError(f"invalid backup_path for {key}")
            resolved_backup = _resolve_within(root, backup, "backup path")
            info["backup_path"] = str(resolved_backup)
        canonical = str(dest)
        if canonical in normalized:
            raise ManifestError(
                f"installed file path collision: {key!r} and {source_keys[canonical]!r} normalize to {canonical}"
            )
        source_keys[canonical] = key
        normalized[canonical] = info

    _validate_mutation_graph(target, root, normalized, manifest_path)
    omissions = _validate_migration_omissions(
        target,
        root,
        normalized,
        manifest.get("migration_omissions"),
        manifest_path,
    )
    return root, normalized, omissions


def validate_manifest(manifest, target_home: str, manifest_path: str):
    """Return (managed_root, normalized_entries) or raise ManifestError."""
    root, entries, _omissions = _validate_v2_manifest(manifest, target_home, manifest_path)
    return root, entries


def build_payload(repo_root: str, target_home: str):
    target = Path(target_home).resolve()
    payload = []

    def _dest(dest_rel: str) -> str:
        raw = target / dest_rel
        _reject_symlink_path(target, raw, "payload destination")
        resolved = raw.resolve()
        if not resolved.is_relative_to(target):
            raise ManifestError(f"payload destination escapes target home: {dest_rel}")
        return str(resolved)

    for src_rel, dest_rel in PAYLOAD:
        payload.append((os.path.join(repo_root, src_rel), _dest(dest_rel)))
    agents_dir = os.path.join(repo_root, "agents")
    if os.path.isdir(agents_dir):
        for name in sorted(os.listdir(agents_dir)):
            if name.endswith(".toml"):
                payload.append(
                    (os.path.join(agents_dir, name), _dest(os.path.join(".codex", "agents", name)))
                )
    return payload


def _target_relative(target: Path, path: Path) -> str:
    """Return a canonical target-home-relative path."""
    return str(path.relative_to(target))


def _legacy_manifest_entries(
    manifest: dict,
    target_home: str,
    manifest_path: str,
    payload_destinations: set[str],
) -> tuple[Path, dict]:
    """Validate the complete legacy v1 manifest before any migration write."""
    if not isinstance(manifest, dict):
        raise ManifestError("legacy manifest root must be an object")
    if type(manifest.get("version")) is not int or manifest.get("version") != 1:
        raise ManifestError("unsupported legacy manifest version")
    installed = manifest.get("installed_files")
    if not isinstance(installed, dict) or not installed:
        raise ManifestError("legacy installed_files must be a non-empty object")

    target = Path(target_home).resolve()
    manifest_canon = Path(manifest_path).resolve()
    normalized = {}
    source_keys = {}
    for key, info in installed.items():
        if not isinstance(key, str) or not Path(key).is_absolute():
            raise ManifestError("legacy installed file paths must be absolute strings")
        if not isinstance(info, dict):
            raise ManifestError("legacy installed_files entries must be objects")
        raw_dest = Path(key)
        _reject_symlink_path(target, raw_dest, "legacy installed file path")
        dest = raw_dest.resolve()
        if not dest.is_relative_to(target):
            raise ManifestError(f"legacy installed file path escapes target home: {key}")
        if dest == manifest_canon:
            raise ManifestError(f"legacy installed file path collides with manifest: {key}")
        if dest == target:
            raise ManifestError("legacy installed file path collides with target home")
        if dest.is_symlink():
            raise ManifestError(f"legacy installed file path is a symlink: {key}")
        canonical = str(dest)
        if canonical in normalized:
            raise ManifestError(
                f"legacy installed file path collision: {key!r} and {source_keys[canonical]!r}"
            )
        legacy_sha = info.get("installed_sha256")
        if not isinstance(legacy_sha, str) or not _SHA_RE.match(legacy_sha):
            raise ManifestError(f"invalid legacy installed_sha256 for {key}")
        legacy_sha = legacy_sha.lower()
        backup = info.get("backup_path")
        if backup is not None:
            if not isinstance(backup, str):
                raise ManifestError(f"invalid legacy backup_path for {key}")
            raw_backup = Path(backup)
            if not raw_backup.is_absolute():
                raw_backup = target / raw_backup
            _reject_symlink_path(target, raw_backup, "legacy backup path")
            resolved_backup = raw_backup.resolve()
            if not resolved_backup.is_relative_to(target):
                raise ManifestError(f"legacy backup path escapes target home: {backup}")
            if resolved_backup in (dest, target, manifest_canon):
                raise ManifestError(f"legacy backup path collides with lifecycle path: {backup}")
        if canonical not in payload_destinations:
            raise ManifestError(f"legacy installed file is not current package payload: {key}")
        source_keys[canonical] = key
        normalized[canonical] = {
            "legacy_sha256": legacy_sha,
        }
    return target, normalized


def _migrate_v1_manifest(
    manifest: dict,
    repo_root: str,
    target_home: str,
    manifest_path: str,
) -> dict:
    """Build a v2 manifest from v1 without touching payload or user files."""
    target = Path(target_home).resolve()
    payload = build_payload(repo_root, target_home)
    payload_destinations = {dest for _src, dest in payload}
    _target, legacy_entries = _legacy_manifest_entries(
        manifest,
        target_home,
        manifest_path,
        payload_destinations,
    )

    installed = {}
    omissions = {}
    for dest, legacy in legacy_entries.items():
        legacy_sha = legacy["legacy_sha256"]
        path = Path(dest)
        if path.exists():
            if path.is_symlink() or not path.is_file():
                raise ManifestError(f"legacy payload path is not a regular file: {dest}")
            current_sha = sha256_of(dest)
            if current_sha == legacy_sha:
                installed[dest] = {
                    "ownership": "managed",
                    "sha256": legacy_sha,
                    "installed_sha256": legacy_sha,
                    "backup_path": None,
                }
                continue
            omissions[_target_relative(target, path)] = {
                "ownership": "unmanaged",
                "state": "modified",
                "legacy_sha256": legacy_sha,
                "migration_sha256": current_sha,
            }
            continue
        omissions[_target_relative(target, path)] = {
            "ownership": "unmanaged",
            "state": "missing",
            "legacy_sha256": legacy_sha,
            "migration_sha256": None,
        }

    migrated = {
        "schema_version": SCHEMA_VERSION,
        "installer_id": INSTALLER_ID,
        "managed_root": str(target),
        "installed_files": installed,
        "migration_omissions": omissions,
    }
    # Reuse v2 validation on the complete candidate before writing it.
    _validate_v2_manifest(migrated, target_home, manifest_path)
    return migrated


def cmd_migrate_manifest_v1(
    repo_root: str,
    target_home: str,
    manifest_path: str,
    dry_run: bool,
) -> None:
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    if not os.path.exists(manifest_path):
        raise ManifestError(f"no legacy manifest found at {manifest_path}")
    raw = read_json(manifest_path)
    migrated = _migrate_v1_manifest(raw, repo_root, target_home, manifest_path)
    if dry_run:
        for dest in migrated["installed_files"]:
            print(f"[DRY-RUN] Would claim managed file: {dest}")
        for rel, info in migrated["migration_omissions"].items():
            print(f"[DRY-RUN] Would preserve {info['state']} omission: {rel}")
        return
    _write_manifest(manifest_path, migrated)
    print(f"Migrated manifest v1 -> v2: {manifest_path}")


def _plan_backup_path(dest: str, managed_root: Path, backup_root: Path) -> str:
    rel = Path(dest).relative_to(managed_root)
    base = f"{backup_root / rel}.pre-orchestrator-backup.{int(time.time())}"
    candidate = base
    counter = 1
    while os.path.exists(candidate):
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _write_manifest(manifest_path: str, manifest: dict) -> None:
    manifest_dir = os.path.dirname(manifest_path)
    os.makedirs(manifest_dir, exist_ok=True)
    tmp = f"{manifest_path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, manifest_path)


def cmd_install(repo_root: str, target_home: str, manifest_path: str, dry_run: bool) -> None:
    target = Path(target_home).resolve()
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    backup_root = _package_backup_root(target)

    old_entries = {}
    migration_omissions = {}
    if os.path.exists(manifest_path):
        raw = read_json(manifest_path)
        _, old_entries, migration_omissions = _validate_v2_manifest(
            raw, target_home, manifest_path
        )

    payload = build_payload(repo_root, target_home)
    for src, _dest in payload:
        if not os.path.isfile(src):
            raise ManifestError(f"payload source missing: {src}")

    active_payload = [
        (src, dest) for src, dest in payload if _target_relative(target, Path(dest)) not in migration_omissions
    ]
    new_entries = {}
    for src, dest in active_payload:
        src_sha = sha256_of(src)
        if dest in old_entries:
            old = old_entries[dest]
            old_sha = old.get("sha256", old.get("installed_sha256"))
            if os.path.exists(dest) and sha256_of(dest) != old_sha:
                raise ManifestError(f"refusing to overwrite modified managed file: {dest}")
            backup = old.get("backup_path")
        else:
            backup = _plan_backup_path(dest, target, backup_root) if os.path.exists(dest) else None
        new_entries[dest] = {
            "ownership": "managed",
            "sha256": src_sha,
            "installed_sha256": src_sha,
            "backup_path": backup,
        }

    new_dest_set = {dest for _, dest in active_payload}
    retired = [(d, old_entries[d]) for d in old_entries if d not in new_dest_set]

    if dry_run:
        for src, dest in payload:
            if _target_relative(target, Path(dest)) in migration_omissions:
                print(f"[DRY-RUN] Skipping explicit migration omission: {dest}")
                continue
            print(f"[DRY-RUN] Would install {src} -> {dest}")
        for dest, _old in retired:
            print(f"[DRY-RUN] Would retire {dest}")
        return

    # Create pre-install backups for destinations that were not previously
    # owned and already existed.
    for src, dest in active_payload:
        info = new_entries[dest]
        backup = info.get("backup_path")
        if dest not in old_entries and backup and not os.path.exists(backup):
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(dest, backup)

    # Install the current payload.
    for src, dest in active_payload:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        if os.path.basename(dest) in EXECUTABLE_PAYLOAD_NAMES:
            os.chmod(dest, 0o755)

    # Retire formerly owned files whose current bytes still match the recorded
    # ownership hash; restore the original backup when present.
    for dest, old in retired:
        if not os.path.exists(dest):
            continue
        old_sha = old.get("sha256", old.get("installed_sha256"))
        if sha256_of(dest) != old_sha:
            continue
        backup = old.get("backup_path")
        if backup and os.path.exists(backup):
            os.replace(backup, dest)
        else:
            os.remove(dest)

    new_manifest = {
        "schema_version": SCHEMA_VERSION,
        "installer_id": INSTALLER_ID,
        "managed_root": str(target),
        "installed_files": new_entries,
    }
    if migration_omissions:
        new_manifest["migration_omissions"] = migration_omissions
    _write_manifest(manifest_path, new_manifest)


def cmd_verify(target_home: str, manifest_path: str) -> None:
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    if not os.path.exists(manifest_path):
        raise ManifestError(f"no installation manifest found at {manifest_path}")
    raw = read_json(manifest_path)
    _, entries, _omissions = _validate_v2_manifest(raw, target_home, manifest_path)

    problems = 0
    for dest, info in entries.items():
        if not os.path.exists(dest):
            print(f"[FAIL] Missing managed file: {dest}", file=sys.stderr)
            problems += 1
            continue
        recorded = info.get("sha256", info.get("installed_sha256"))
        if sha256_of(dest) != recorded:
            print(f"[FAIL] Modified managed file: {dest}", file=sys.stderr)
            problems += 1
    if problems:
        raise ManifestError(f"{problems} managed file(s) modified or missing")


def cmd_uninstall(target_home: str, manifest_path: str) -> None:
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    if not os.path.exists(manifest_path):
        raise ManifestError(f"no installation manifest found at {manifest_path}")
    raw = read_json(manifest_path)
    _, entries, _omissions = _validate_v2_manifest(raw, target_home, manifest_path)

    # Preflight every entry before the first mutation so a single ownership
    # ambiguity aborts the whole operation without touching anything.
    for dest, info in entries.items():
        if not os.path.exists(dest):
            continue
        recorded = info.get("sha256", info.get("installed_sha256"))
        if sha256_of(dest) != recorded:
            raise ManifestError(f"refusing to remove modified managed file: {dest}")

    for dest, info in entries.items():
        if not os.path.exists(dest):
            continue
        backup = info.get("backup_path")
        if backup and os.path.exists(backup):
            os.replace(backup, dest)
            print(f"[RESTORED] Pre-existing file restored: {dest} (from {backup})")
        else:
            os.remove(dest)
            print(f"[REMOVED] Cleanly removed package file: {dest}")

    os.remove(manifest_path)
    print("Removed manifest file.")


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    if len(argv) < 2:
        print(
            "usage: installer_lifecycle.py <install|verify|uninstall|migrate-manifest-v1> [options]",
            file=sys.stderr,
        )
        return 2

    cmd = argv[1]
    opts = {}
    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg == "--dry-run":
            opts["dry_run"] = True
            i += 1
        elif arg in ("--target-home", "--repo-root", "--manifest-path"):
            if i + 1 >= len(argv):
                print(f"missing value for {arg}", file=sys.stderr)
                return 2
            opts[arg[2:].replace("-", "_")] = argv[i + 1]
            i += 2
        else:
            print(f"unknown option: {arg}", file=sys.stderr)
            return 2

    target_home = opts.get("target_home") or os.environ.get("HOME") or "."
    manifest_path = opts.get("manifest_path") or os.path.join(target_home, MANIFEST_REL)

    try:
        if cmd == "install":
            repo_root = opts.get("repo_root")
            if not repo_root:
                print("install requires --repo-root", file=sys.stderr)
                return 2
            cmd_install(repo_root, target_home, manifest_path, bool(opts.get("dry_run")))
        elif cmd == "migrate-manifest-v1":
            repo_root = opts.get("repo_root")
            if not repo_root:
                print("migrate-manifest-v1 requires --repo-root", file=sys.stderr)
                return 2
            cmd_migrate_manifest_v1(
                repo_root,
                target_home,
                manifest_path,
                bool(opts.get("dry_run")),
            )
        elif cmd == "verify":
            cmd_verify(target_home, manifest_path)
        elif cmd == "uninstall":
            cmd_uninstall(target_home, manifest_path)
        else:
            print(f"unknown command: {cmd}", file=sys.stderr)
            return 2
    except ManifestError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
