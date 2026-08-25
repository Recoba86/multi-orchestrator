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
MIGRATION_CLASSIFICATIONS = frozenset(
    ("preserved_customized", "pristine", "repaired_missing", "new_payload")
)
MIGRATION_PROVENANCE_SCHEMA = 1


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


def _validate_migration_provenance(
    target: Path,
    root: Path,
    installed: dict,
    omissions: dict,
    provenance,
) -> dict | None:
    """Validate the audit trail without making it an ownership source."""
    if provenance is None:
        return None
    if not isinstance(provenance, dict):
        raise ManifestError("migration_provenance must be an object")
    if provenance.get("schema_version") != MIGRATION_PROVENANCE_SCHEMA:
        raise ManifestError("unsupported migration_provenance schema_version")
    if provenance.get("from_schema_version") != 1:
        raise ManifestError("migration_provenance must identify v1 source")
    legacy_digest = provenance.get("legacy_manifest_sha256")
    if not isinstance(legacy_digest, str) or not _SHA_RE.fullmatch(legacy_digest):
        raise ManifestError("migration_provenance legacy manifest hash is invalid")
    classifications = provenance.get("classifications")
    if not isinstance(classifications, dict) or not classifications:
        raise ManifestError("migration_provenance classifications must be a non-empty object")

    installed_set = set(installed)
    omission_set = {
        str((target / rel).resolve()) for rel in omissions
    }
    normalized = {}
    counts = {state: 0 for state in MIGRATION_CLASSIFICATIONS}
    for raw_path, state in classifications.items():
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise ManifestError("migration provenance paths must be absolute")
        path = Path(raw_path)
        _reject_symlink_path(target, path, "migration provenance path")
        path = path.resolve()
        if not path.is_relative_to(target) or not path.is_relative_to(root):
            raise ManifestError(f"migration provenance path escapes managed root: {raw_path}")
        canonical = str(path)
        if canonical != raw_path:
            raise ManifestError(f"migration provenance path is not canonical: {raw_path}")
        if state not in MIGRATION_CLASSIFICATIONS:
            raise ManifestError(f"unknown migration classification for {raw_path}")
        if state == "preserved_customized":
            if canonical not in omission_set:
                raise ManifestError(
                    f"preserved classification lacks migration omission: {raw_path}"
                )
        elif canonical not in installed_set:
            raise ManifestError(f"managed migration classification lacks installed entry: {raw_path}")
        normalized[canonical] = state
        counts[state] += 1

    expected_paths = installed_set | omission_set
    if set(normalized) != expected_paths:
        missing = sorted(expected_paths - set(normalized))
        extra = sorted(set(normalized) - expected_paths)
        raise ManifestError(
            "migration_provenance must classify each installed or preserved path exactly once "
            f"(missing={missing!r}, extra={extra!r})"
        )

    declared_counts = provenance.get("counts")
    if declared_counts is not None:
        if not isinstance(declared_counts, dict):
            raise ManifestError("migration_provenance counts must be an object")
        for state, count in counts.items():
            if declared_counts.get(state) != count:
                raise ManifestError(f"migration_provenance count mismatch for {state}")
        if set(declared_counts) - set(counts):
            raise ManifestError("migration_provenance has unknown count keys")
    return {
        "schema_version": MIGRATION_PROVENANCE_SCHEMA,
        "from_schema_version": 1,
        "legacy_manifest_sha256": legacy_digest.lower(),
        "classifications": normalized,
        "counts": counts,
    }


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
    provenance = _validate_migration_provenance(
        target,
        root,
        normalized,
        omissions,
        manifest.get("migration_provenance"),
    )
    return root, normalized, omissions, provenance


def validate_manifest(manifest, target_home: str, manifest_path: str):
    """Return (managed_root, normalized_entries) or raise ManifestError."""
    root, entries, _omissions, _provenance = _validate_v2_manifest(
        manifest, target_home, manifest_path
    )
    return root, entries


def build_payload(repo_root: str, target_home: str):
    target = Path(target_home).resolve()
    source_root = Path(repo_root).resolve()
    payload = []

    def _dest(dest_rel: str) -> str:
        raw = target / dest_rel
        _reject_symlink_path(target, raw, "payload destination")
        resolved = raw.resolve()
        if not resolved.is_relative_to(target):
            raise ManifestError(f"payload destination escapes target home: {dest_rel}")
        return str(resolved)

    for src_rel, dest_rel in PAYLOAD:
        source = Path(repo_root) / src_rel
        if source.is_symlink() or not source.resolve().is_relative_to(source_root):
            raise ManifestError(f"payload source escapes repository root: {source}")
        payload.append((str(source), _dest(dest_rel)))
    agents_dir = os.path.join(repo_root, "agents")
    if os.path.isdir(agents_dir):
        for name in sorted(os.listdir(agents_dir)):
            if name.endswith(".toml"):
                source = Path(agents_dir) / name
                if source.is_symlink() or not source.resolve().is_relative_to(source_root):
                    raise ManifestError(f"payload source escapes repository root: {source}")
                payload.append(
                    (str(source), _dest(os.path.join(".codex", "agents", name)))
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
    backup_owners = {}
    reserved = {str((target / rel).resolve()) for rel in RESERVED_UNMANAGED_RELS}
    backup_root = _package_backup_root(target)
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
        if "sha256" in info:
            if not isinstance(info["sha256"], str) or not _SHA_RE.fullmatch(info["sha256"]):
                raise ManifestError(f"invalid legacy sha256 for {key}")
            if info["sha256"].lower() != legacy_sha:
                raise ManifestError(f"conflicting legacy hashes for {key}")
        backup = info.get("backup_path")
        backup_sha = info.get("backup_sha256")
        if backup_sha is not None and (
            not isinstance(backup_sha, str) or not _SHA_RE.fullmatch(backup_sha)
        ):
            raise ManifestError(f"invalid legacy backup_sha256 for {key}")
        if backup is None and backup_sha is not None:
            raise ManifestError(f"legacy backup_sha256 requires backup_path for {key}")
        if backup is not None:
            if not isinstance(backup, str):
                raise ManifestError(f"invalid legacy backup_path for {key}")
            raw_backup = Path(backup)
            if not raw_backup.is_absolute():
                raw_backup = target / raw_backup
            if Path(os.path.normpath(str(raw_backup))) != raw_backup:
                raise ManifestError(f"legacy backup path must be normalized: {backup}")
            _reject_symlink_path(target, raw_backup, "legacy backup path")
            resolved_backup = raw_backup.resolve()
            if not resolved_backup.is_relative_to(target):
                raise ManifestError(f"legacy backup path escapes target home: {backup}")
            if resolved_backup in (dest, target, manifest_canon):
                raise ManifestError(f"legacy backup path collides with lifecycle path: {backup}")
            backup_canon = str(resolved_backup)
            if backup_canon in reserved or any(
                Path(backup_canon).is_relative_to(Path(profile)) for profile in reserved
            ):
                raise ManifestError(f"legacy backup path overlaps reserved config: {backup}")
            if resolved_backup == backup_root or resolved_backup.is_relative_to(backup_root):
                # A v1 backup already in the confined v2 root can be retained,
                # but it still must be unique and regular.
                pass
            if backup_canon in backup_owners:
                raise ManifestError(f"legacy backup path collision: {backup}")
            backup_owners[backup_canon] = canonical
            if resolved_backup.is_symlink() or not resolved_backup.is_file():
                raise ManifestError(f"legacy backup path is not a regular file: {backup}")
            expected_backup = backup_sha.lower() if isinstance(backup_sha, str) else legacy_sha
            if sha256_of(str(resolved_backup)) != expected_backup:
                raise ManifestError(f"legacy backup hash mismatch: {backup}")
        if canonical not in payload_destinations:
            raise ManifestError(f"legacy installed file is not current package payload: {key}")
        source_keys[canonical] = key
        normalized[canonical] = {
            "legacy_sha256": legacy_sha,
            "backup_path": str(resolved_backup) if backup is not None else None,
            "backup_sha256": backup_sha.lower() if isinstance(backup_sha, str) else None,
        }
    destination_set = set(normalized)
    for backup, owner in backup_owners.items():
        if backup in destination_set:
            raise ManifestError(f"legacy backup collides with installed file: {backup}")
        backup_path = Path(backup)
        for destination in destination_set:
            if backup_path == Path(destination) or backup_path.is_relative_to(Path(destination)):
                raise ManifestError(f"legacy backup overlaps installed path: {backup}")
    return target, normalized


def _migrate_v1_manifest(
    manifest: dict,
    repo_root: str,
    target_home: str,
    manifest_path: str,
    legacy_manifest_sha256: str | None = None,
) -> tuple[dict, dict]:
    """Build a v2 manifest and an all-or-nothing file mutation plan."""
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
    classifications = {}
    writes = []
    backup_copies = []
    backup_removals = []
    touched = {str(Path(manifest_path).resolve())}
    source_by_dest = {dest: src for src, dest in payload}
    agent_destinations = {
        dest for dest in payload_destinations
        if Path(dest).parent == target / ".codex" / "agents"
    }

    def _regular(path: Path, label: str) -> None:
        if path.is_symlink() or not path.is_file():
            raise ManifestError(f"{label} is not a regular file: {path}")

    def _plan_backup(dest: str, legacy: dict | None, *, existing: bool) -> str | None:
        """Validate a legacy backup or plan a confined backup for a new file."""
        source_backup = legacy.get("backup_path") if legacy else None
        if source_backup:
            source = Path(source_backup)
            _regular(source, "legacy backup")
            expected = legacy.get("backup_sha256") or legacy["legacy_sha256"]
            if sha256_of(str(source)) != expected:
                raise ManifestError(f"legacy backup hash mismatch: {source}")
            confined = source.is_relative_to(_package_backup_root(target))
            if confined:
                return str(source)
            destination = _plan_backup_path(dest, target, _package_backup_root(target))
            if destination in touched:
                raise ManifestError(f"backup path collides with planned mutation: {destination}")
            backup_copies.append((str(source), destination))
            backup_removals.append(str(source))
            touched.update((str(source), destination))
            return destination
        if existing:
            destination = _plan_backup_path(dest, target, _package_backup_root(target))
            if destination in touched:
                raise ManifestError(f"backup path collides with planned mutation: {destination}")
            backup_copies.append((dest, destination))
            touched.add(destination)
            return destination
        return None

    # First classify every legacy entry and reject every unsafe conflict.  No
    # filesystem mutation occurs in this pass.
    for dest, legacy in legacy_entries.items():
        legacy_sha = legacy["legacy_sha256"]
        path = Path(dest)
        if path.exists():
            _regular(path, "legacy payload path")
            current_sha = sha256_of(dest)
            if current_sha == legacy_sha:
                backup = _plan_backup(dest, legacy, existing=False)
                installed[dest] = {
                    "ownership": "managed",
                    "sha256": sha256_of(source_by_dest[dest]),
                    "installed_sha256": sha256_of(source_by_dest[dest]),
                    "backup_path": backup,
                }
                touched.add(dest)
                classifications[dest] = "pristine"
                if installed[dest]["sha256"] != current_sha:
                    writes.append((source_by_dest[dest], dest))
                continue
            if dest not in agent_destinations:
                raise ManifestError(f"modified non-agent payload blocks migration: {dest}")
            # User-customized declarations are explicitly preserved as
            # unmanaged bytes; they are never included in installed_files.
            omissions[_target_relative(target, path)] = {
                "ownership": "unmanaged",
                "state": "modified",
                "legacy_sha256": legacy_sha,
                "migration_sha256": current_sha,
            }
            classifications[dest] = "preserved_customized"
            continue

        source = Path(source_by_dest[dest])
        _regular(source, "current payload source")
        backup = _plan_backup(dest, legacy, existing=False)
        src_sha = sha256_of(str(source))
        installed[dest] = {
            "ownership": "managed",
            "sha256": src_sha,
            "installed_sha256": src_sha,
            "backup_path": backup,
        }
        touched.add(dest)
        writes.append((str(source), dest))
        classifications[dest] = "repaired_missing"

    # Any current payload omitted by v1 is a new package file and is installed
    # from the validated source, with a user baseline backup when needed.
    for source, dest in payload:
        if dest in legacy_entries:
            continue
        source_path = Path(source)
        _regular(source_path, "current payload source")
        existing = Path(dest).exists()
        if existing:
            _regular(Path(dest), "new payload destination")
        src_sha = sha256_of(source)
        if existing:
            if sha256_of(dest) != src_sha:
                raise ManifestError(
                    f"UNKNOWN_CONFLICT: omitted v1 payload already exists with unknown bytes: {dest}"
                )
            # The destination already contains the exact current payload.  It
            # is safe to claim it without rewriting or creating a backup.
            installed[dest] = {
                "ownership": "managed",
                "sha256": src_sha,
                "installed_sha256": src_sha,
                "backup_path": None,
            }
            touched.add(dest)
            classifications[dest] = "new_payload"
            continue
        backup = _plan_backup(dest, None, existing=False)
        installed[dest] = {
            "ownership": "managed",
            "sha256": src_sha,
            "installed_sha256": src_sha,
            "backup_path": backup,
        }
        touched.add(dest)
        writes.append((source, dest))
        classifications[dest] = "new_payload"

    migrated = {
        "schema_version": SCHEMA_VERSION,
        "installer_id": INSTALLER_ID,
        "managed_root": str(target),
        "installed_files": installed,
        "migration_omissions": omissions,
    }
    migrated["migration_provenance"] = {
        "schema_version": MIGRATION_PROVENANCE_SCHEMA,
        "from_schema_version": 1,
        "legacy_manifest_sha256": legacy_manifest_sha256 or ("0" * 64),
        "classifications": classifications,
        "counts": {
            state: sum(value == state for value in classifications.values())
            for state in MIGRATION_CLASSIFICATIONS
        },
    }
    # Reuse v2 validation on the complete candidate before writing it.
    _validate_v2_manifest(migrated, target_home, manifest_path)
    plan = {
        "writes": writes,
        "backup_copies": backup_copies,
        "backup_removals": backup_removals,
        "touched": touched,
    }
    return migrated, plan


def cmd_migrate_manifest_v1(
    repo_root: str,
    target_home: str,
    manifest_path: str,
    dry_run: bool,
) -> None:
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    if not os.path.exists(manifest_path):
        raise ManifestError(f"no legacy manifest found at {manifest_path}")
    try:
        legacy_bytes = Path(manifest_path).read_bytes()
    except OSError as exc:
        raise ManifestError(f"failed to read legacy manifest {manifest_path}: {exc}")
    raw = read_json(manifest_path)
    legacy_digest = hashlib.sha256(legacy_bytes).hexdigest()
    migrated, plan = _migrate_v1_manifest(
        raw,
        repo_root,
        target_home,
        manifest_path,
        legacy_digest,
    )
    if dry_run:
        for source, dest in plan["writes"]:
            state = migrated["migration_provenance"]["classifications"][dest]
            print(f"[DRY-RUN] {state}: {source} -> {dest}")
        for source, dest in plan["backup_copies"]:
            print(f"[DRY-RUN] Would retain backup: {source} -> {dest}")
        for rel, info in migrated.get("migration_omissions", {}).items():
            print(f"[DRY-RUN] Would preserve {info['state']} omission: {rel}")
        return

    # Snapshot every file touched by the complete plan.  If any controlled
    # operation fails, restore the exact bytes/modes and the exact v1 manifest.
    snapshot = {}
    for raw_path in plan["touched"] | {
        dest for _src, dest in plan["writes"]
    } | {
        dest for _src, dest in plan["backup_copies"]
    } | set(plan["backup_removals"]):
        path = Path(raw_path)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ManifestError(f"migration mutation path is not a regular file: {path}")
        if path.exists():
            snapshot[str(path)] = (path.read_bytes(), path.stat().st_mode)
        else:
            snapshot[str(path)] = None

    def restore() -> None:
        for raw_path, state in snapshot.items():
            path = Path(raw_path)
            try:
                if state is None:
                    if path.is_symlink() or path.is_file():
                        path.unlink()
                    continue
                data, mode = state
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(f".{path.name}.rollback.{os.getpid()}")
                tmp.write_bytes(data)
                os.replace(tmp, path)
                os.chmod(path, mode & 0o7777)
            except OSError:
                # Preserve the original failure; rollback is best effort after
                # a filesystem-level error and never masks it.
                pass

    try:
        for source, destination in plan["backup_copies"]:
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        for source, destination in plan["writes"]:
            Path(destination).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if os.path.basename(destination) in EXECUTABLE_PAYLOAD_NAMES:
                os.chmod(destination, 0o755)
        for source in plan["backup_removals"]:
            Path(source).unlink()
        _write_manifest(manifest_path, migrated)
    except (OSError, ManifestError):
        restore()
        raise
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
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, manifest_path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def cmd_install(repo_root: str, target_home: str, manifest_path: str, dry_run: bool) -> None:
    target = Path(target_home).resolve()
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    backup_root = _package_backup_root(target)

    old_entries = {}
    migration_omissions = {}
    migration_provenance = None
    if os.path.exists(manifest_path):
        raw = read_json(manifest_path)
        _, old_entries, migration_omissions, migration_provenance = _validate_v2_manifest(
            raw, target_home, manifest_path
        )

    payload = build_payload(repo_root, target_home)
    for src, _dest in payload:
        if not os.path.isfile(src):
            raise ManifestError(f"payload source missing: {src}")

    active_payload = [
        (src, dest)
        for src, dest in payload
        if migration_omissions.get(_target_relative(target, Path(dest)), {}).get("state")
        != "modified"
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
    remaining_omissions = {
        rel: info
        for rel, info in migration_omissions.items()
        if info.get("state") == "modified"
    }
    if remaining_omissions:
        new_manifest["migration_omissions"] = remaining_omissions
    if migration_provenance is not None:
        classifications = dict(migration_provenance["classifications"])
        for rel, info in migration_omissions.items():
            if info.get("state") == "missing":
                classifications[str((target / rel).resolve())] = "repaired_missing"
        classifications = {
            dest: state
            for dest, state in classifications.items()
            if dest in new_entries or state == "preserved_customized"
        }
        new_manifest["migration_provenance"] = {
            "schema_version": MIGRATION_PROVENANCE_SCHEMA,
            "from_schema_version": 1,
            "legacy_manifest_sha256": migration_provenance["legacy_manifest_sha256"],
            "classifications": classifications,
            "counts": {
                state: sum(value == state for value in classifications.values())
                for state in MIGRATION_CLASSIFICATIONS
            },
        }
    _write_manifest(manifest_path, new_manifest)


def cmd_verify(target_home: str, manifest_path: str) -> None:
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    if not os.path.exists(manifest_path):
        raise ManifestError(f"no installation manifest found at {manifest_path}")
    raw = read_json(manifest_path)
    _, entries, omissions, _provenance = _validate_v2_manifest(raw, target_home, manifest_path)

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
    # Preserved declarations remain user-owned, but they are still part of the
    # verifier's observable surface: a deleted declaration is a failure and a
    # later shell-level TOML/policy check must inspect its bytes.
    for rel, info in omissions.items():
        dest = str((Path(target_home).resolve() / rel).resolve())
        if not os.path.isfile(dest) or os.path.islink(dest):
            print(f"[FAIL] Missing preserved user file: {dest}", file=sys.stderr)
            problems += 1
    if problems:
        raise ManifestError(f"{problems} managed or preserved file(s) modified or missing")


def cmd_uninstall(target_home: str, manifest_path: str) -> None:
    manifest_path = str(_resolve_manifest_path(target_home, manifest_path))
    if not os.path.exists(manifest_path):
        raise ManifestError(f"no installation manifest found at {manifest_path}")
    raw = read_json(manifest_path)
    _, entries, _omissions, _provenance = _validate_v2_manifest(raw, target_home, manifest_path)

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
