"""Centralized provider-agnostic policy for Auto Team and advisory roles.

This module is the single declarative surface for the policy rules used by the
resolver. It defines the public logical roles, the outcome taxonomy, the fixed
hard-constraint stage order, and the deterministic advisory tie-break order.

The four public roles here are provider-agnostic *logical* roles. They are
distinct from the normative RC3 endpoint/role chains in
``core/ORCHESTRATOR_CORE.md`` (``SCOUT``, ``STANDARD_WORKER``, ``DEEP_WORKER``,
``VERIFIER``, ``PREMIUM_SECOND_OPINION``); this module never modifies or reuses
that routing.

Configuration mutations are permitted only through explicit, validated,
stale-checked, byte-exact-backup, atomic APIs (apply_role_selections,
mutate_configuration_file); hidden mutations, network calls, active probing,
Host interaction, web research, and credential handling remain strictly excluded.
Identities are matched exactly, never via aliases or fuzzy normalization.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

from core.model_capabilities import CAPABILITY_LABELS
from core.model_intelligence import (
    MIN_ROLE_COVERAGE,
    ROLE_RECOMMENDATION_WEIGHTS,
)


PUBLIC_ROLES = ("planner", "scout", "worker", "reviewer")
ROLE_FIELDS = ("requires", "preferred", "fallback", "capability_hints")
OPERATOR_ROLES = (
    "BOSS",
    "SCOUT",
    "STANDARD_WORKER",
    "DEEP_WORKER",
    "VERIFIER",
    "PREMIUM_SECOND_OPINION",
)
OPERATOR_POLICY_FIELDS = ("model", "effort")
ADVISORY_TO_OPERATOR_ROLE = {
    "planner": "BOSS",
    "scout": "SCOUT",
    "worker": "STANDARD_WORKER",
    "reviewer": "VERIFIER",
}

# Fixed advisory role weights and the coverage gate remain defined in
# ``model_intelligence``; these aliases give the policy a single import surface.
ROLE_WEIGHTS = ROLE_RECOMMENDATION_WEIGHTS
ROLE_COVERAGE_THRESHOLD = MIN_ROLE_COVERAGE
CAPABILITIES = CAPABILITY_LABELS

OUTCOME_RECOMMENDED = "RECOMMENDED"
OUTCOME_UNRESOLVED = "UNRESOLVED"
OUTCOME_REJECTED = "REJECTED"
OUTCOME_UNKNOWN = "UNKNOWN"

# Hard constraints run before any advisory ranking. Order is meaningful: each
# stage only runs when every earlier stage passed.
HARD_CONSTRAINTS = (
    "exact_configured_identity",
    "discovered_identity",
    "availability_not_unavailable",
)

# Deterministic advisory tie-break, applied in this exact order.
TIE_BREAK = (
    "weighted_score_desc",
    "coverage_desc",
    "confidence_desc",
    "raw_identity_asc",
)


class ConfigurationError(ValueError):
    """A concise, user-facing configuration error."""


@dataclass(frozen=True)
class MutationResult:
    applied: bool
    config_path: Path
    before_sha256: str
    after_sha256: str
    backup_path: Path | None
    updated_configuration: dict[str, Any]


def _read_yaml(path: Path) -> object:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigurationError("YAML parser unavailable") from exc

    try:
        with path.open("r", encoding="utf-8") as source:
            return yaml.safe_load(source)
    except FileNotFoundError as exc:
        raise ConfigurationError("configuration file not found") from exc
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError("configuration file is unreadable") from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError("YAML parse failure") from exc


def _validate_operator_policy(value: object) -> dict[str, list[dict[str, str]]]:
    """Validate the canonical raw model/effort chains without reordering."""
    if not isinstance(value, Mapping):
        raise ConfigurationError("operator_policy must be a mapping")

    unknown_roles = [key for key in value if key not in OPERATOR_ROLES]
    if unknown_roles:
        raise ConfigurationError(
            f"operator_policy contains unknown role(s): {sorted(unknown_roles)}"
        )
    missing_roles = [role for role in OPERATOR_ROLES if role not in value]
    if missing_roles:
        raise ConfigurationError(
            f"operator_policy missing required role(s): {', '.join(missing_roles)}"
        )

    result: dict[str, list[dict[str, str]]] = {}
    for role in OPERATOR_ROLES:
        entries = value[role]
        if not isinstance(entries, list) or not entries:
            raise ConfigurationError(
                f"operator_policy.{role} must be a non-empty list"
            )
        parsed: list[dict[str, str]] = []
        seen_models: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                raise ConfigurationError(
                    f"operator_policy.{role}[{index}] must be a mapping"
                )
            unknown_fields = [
                field for field in entry if field not in OPERATOR_POLICY_FIELDS
            ]
            if unknown_fields:
                raise ConfigurationError(
                    f"operator_policy.{role}[{index}] contains unknown field(s): "
                    f"{sorted(unknown_fields)}"
                )
            missing_fields = [
                field for field in OPERATOR_POLICY_FIELDS if field not in entry
            ]
            if missing_fields:
                raise ConfigurationError(
                    f"operator_policy.{role}[{index}] missing field(s): "
                    f"{', '.join(missing_fields)}"
                )
            model = entry["model"]
            effort = entry["effort"]
            if type(model) is not str or not model.strip():
                raise ConfigurationError(
                    f"operator_policy.{role}[{index}].model must be a non-empty string"
                )
            if type(effort) is not str or not effort.strip():
                raise ConfigurationError(
                    f"operator_policy.{role}[{index}].effort must be a non-empty string"
                )
            if model in seen_models:
                raise ConfigurationError(
                    f"operator_policy.{role} contains duplicate model {model!r}"
                )
            seen_models.add(model)
            parsed.append({"model": model, "effort": effort})
        result[role] = parsed
    return result


def validate_configuration(value: object) -> dict[str, Any]:
    """Validate advisory roles and an optional canonical operator policy."""
    if not isinstance(value, Mapping):
        raise ConfigurationError("configuration root must be a mapping")

    unknown_roles = [
        key for key in value if key not in PUBLIC_ROLES and key != "operator_policy"
    ]
    if unknown_roles:
        raise ConfigurationError(
            f"configuration contains unknown role(s) (unknown top-level keys or roles: {sorted(unknown_roles)})"
        )

    missing_roles = [role for role in PUBLIC_ROLES if role not in value]
    if missing_roles:
        raise ConfigurationError(
            f"configuration missing required role(s): {', '.join(missing_roles)} (missing roles: {sorted(missing_roles)})"
        )

    result: dict[str, Any] = {}
    for role, entry in value.items():
        if role == "operator_policy":
            result[role] = _validate_operator_policy(entry)
            continue
        if not isinstance(entry, Mapping):
            raise ConfigurationError(f"{role} must be a mapping")

        unknown_fields = [field for field in entry if field not in ROLE_FIELDS]
        if unknown_fields:
            raise ConfigurationError(
                f"{role} contains unknown field(s) (unknown fields: {sorted(unknown_fields)})"
            )

        missing_fields = [field for field in ROLE_FIELDS if field not in entry]
        if missing_fields:
            raise ConfigurationError(
                f"{role} missing required field(s): {', '.join(missing_fields)} (missing fields: {sorted(missing_fields)})"
            )

        role_entry: dict[str, list[str]] = {}
        for field, items in entry.items():
            if not isinstance(items, list) or not items:
                raise ConfigurationError(f"{role}.{field} must be a non-empty list")
            if any(type(item) is not str or not item.strip() for item in items):
                raise ConfigurationError(
                    f"{role}.{field} must contain only non-empty strings (non-empty strings)"
                )
            role_entry[field] = list(items)
        result[role] = role_entry

    operator_policy = result.get("operator_policy")
    if operator_policy is not None:
        for advisory_role, operator_role in ADVISORY_TO_OPERATOR_ROLE.items():
            expected = tuple(
                entry["model"] for entry in operator_policy[operator_role]
            )
            actual: list[str] = []
            seen: set[str] = set()
            for field in ("preferred", "fallback"):
                for model in result[advisory_role][field]:
                    if model not in seen:
                        seen.add(model)
                        actual.append(model)
            if tuple(actual) != expected:
                raise ConfigurationError(
                    f"{advisory_role} preferred+fallback does not match "
                    f"operator_policy.{operator_role}"
                )

    return result


def load_configuration(path: str | Path) -> dict[str, Any]:
    """Read and validate one configuration file safely."""
    p = Path(path).expanduser()
    if p.is_symlink():
        raise ConfigurationError("configuration file cannot be a symlink")
    if not p.exists():
        raise ConfigurationError("configuration file not found")
    if not p.is_file():
        raise ConfigurationError("configuration file is unreadable")
    return validate_configuration(_read_yaml(p))


def compute_file_sha256(path: str | Path) -> str:
    """Compute SHA-256 of a regular, non-symlink file."""
    p = Path(path).expanduser()
    if p.is_symlink():
        raise ConfigurationError("configuration file cannot be a symlink")
    if not p.is_file():
        raise ConfigurationError("configuration file not found or unreadable")
    try:
        content = p.read_bytes()
    except OSError as exc:
        raise ConfigurationError("configuration file is unreadable") from exc
    return hashlib.sha256(content).hexdigest()


def apply_role_selections(
    configuration: Mapping[str, Any],
    selections: Mapping[str, str],
) -> dict[str, Any]:
    """Move exact selected identity to the front of role preferred list."""
    if not isinstance(selections, Mapping):
        raise ConfigurationError("selections must be a mapping")

    configuration = validate_configuration(configuration)

    for role, model in selections.items():
        if not is_public_role(role):
            raise ConfigurationError(f"unknown role: {role!r}")
        if not isinstance(model, str) or not model.strip():
            raise ConfigurationError(
                f"model for role {role!r} must be a non-empty string"
            )

    updated: dict[str, Any] = {}
    for role, entry in configuration.items():
        if role == "operator_policy":
            updated[role] = {
                operator_role: [dict(item) for item in entries]
                for operator_role, entries in entry.items()
            }
            continue
        updated[role] = {field: list(items) for field, items in entry.items()}
        if role in selections:
            selected_model = selections[role]
            old_preferred = updated[role]["preferred"]
            new_preferred = [selected_model] + [
                m for m in old_preferred if m != selected_model
            ]
            updated[role]["preferred"] = new_preferred

    operator_policy = updated.get("operator_policy")
    if operator_policy is not None:
        for advisory_role, selected_model in selections.items():
            operator_role = ADVISORY_TO_OPERATOR_ROLE[advisory_role]
            entries = operator_policy[operator_role]
            selected = next(
                (entry for entry in entries if entry["model"] == selected_model),
                None,
            )
            if selected is None:
                raise ConfigurationError(
                    f"model {selected_model!r} is not present in canonical "
                    f"operator_policy.{operator_role}"
                )
            entries.remove(selected)
            entries.insert(0, selected)

    return validate_configuration(updated)


def mutate_configuration_file(
    path: str | Path,
    selections: Mapping[str, str],
    *,
    expected_sha256: str | None = None,
    dry_run: bool = True,
    approved: bool = False,
) -> MutationResult:
    """Safely apply role model selections to a configuration file with rollback."""
    p = Path(os.path.abspath(Path(path).expanduser()))
    parent = p.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ConfigurationError(
            "configuration parent directory is invalid or unsafe (symlinked or non-directory)"
        )
    if p.is_symlink():
        raise ConfigurationError("configuration file cannot be a symlink")
    if not p.exists():
        raise ConfigurationError("configuration file not found")
    if not p.is_file():
        raise ConfigurationError("configuration file is not a regular file")

    try:
        current_bytes = p.read_bytes()
    except OSError as exc:
        raise ConfigurationError("configuration file is unreadable") from exc

    current_sha256 = hashlib.sha256(current_bytes).hexdigest()

    if expected_sha256 is not None:
        if current_sha256.lower() != expected_sha256.strip().lower():
            raise ConfigurationError(
                f"SHA-256 mismatch: expected {expected_sha256}, got {current_sha256}"
            )

    current_config = load_configuration(p)
    updated_config = apply_role_selections(current_config, selections)

    try:
        import yaml
    except ImportError as exc:
        raise ConfigurationError("YAML parser unavailable") from exc

    try:
        new_content = yaml.safe_dump(updated_config, sort_keys=False)
    except Exception as exc:
        raise ConfigurationError("configuration serialization failed") from exc
    if not isinstance(new_content, str):
        raise ConfigurationError("configuration serializer must return text")
    try:
        new_bytes = new_content.encode("utf-8")
    except Exception as exc:
        raise ConfigurationError("configuration encoding failed") from exc
    if not isinstance(new_bytes, bytes):
        raise ConfigurationError("configuration encoding failed")
    try:
        emitted_value = yaml.safe_load(new_bytes)
        updated_config = validate_configuration(emitted_value)
    except ConfigurationError as exc:
        raise ConfigurationError(f"serialized configuration schema invalid: {exc}") from exc
    except Exception as exc:
        raise ConfigurationError("configuration emitted YAML parse failure") from exc
    new_sha256 = hashlib.sha256(new_bytes).hexdigest()

    if dry_run:
        return MutationResult(
            applied=False,
            config_path=p,
            before_sha256=current_sha256,
            after_sha256=new_sha256,
            backup_path=None,
            updated_configuration=updated_config,
        )

    if not approved:
        raise ConfigurationError("mutation requires explicit approval flag")
    if expected_sha256 is None:
        raise ConfigurationError("mutation requires expected SHA-256")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    counter = 0
    backup_path: Path | None = None
    while True:
        suffix = (
            f".bak.{timestamp}_{os.getpid()}_{counter}"
            if counter
            else f".bak.{timestamp}_{os.getpid()}"
        )
        candidate = parent / f"{p.name}{suffix}"
        try:
            fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as bf:
                bf.write(current_bytes)
                bf.flush()
                os.fsync(bf.fileno())
            backup_path = candidate
            break
        except FileExistsError:
            counter += 1
            if counter > 1000:
                raise ConfigurationError(
                    "failed to allocate collision-safe backup file"
                )

    temp_path: Path | None = None
    try:
        orig_mode = os.stat(p).st_mode & 0o777
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=parent, prefix=f".{p.name}.tmp.", delete=False
        ) as tf:
            temp_path = Path(tf.name)
            os.chmod(temp_path, orig_mode)
            tf.write(new_bytes)
            tf.flush()
            os.fsync(tf.fileno())

        os.replace(temp_path, p)
        temp_path = None

        try:
            dir_fd = os.open(str(parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception as exc:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise ConfigurationError(f"configuration mutation failed: {exc}") from exc

    return MutationResult(
        applied=True,
        config_path=p,
        before_sha256=current_sha256,
        after_sha256=new_sha256,
        backup_path=backup_path,
        updated_configuration=updated_config,
    )


def is_public_role(role: object) -> bool:
    """Return True only for an exact, known public logical role name."""
    return type(role) is str and role in PUBLIC_ROLES


def configured_role_identifiers(
    configuration: Mapping[str, Mapping[str, object]], role: str
) -> tuple[str, ...]:
    """Return ``preferred`` then ``fallback`` exact identifiers for one role.

    Exact raw strings are preserved in configured order. Duplicate exact
    strings are dropped after their first occurrence; no aliasing or
    normalization is applied.
    """
    if not is_public_role(role) or not isinstance(configuration, Mapping):
        return ()
    entry = configuration.get(role)
    if not isinstance(entry, Mapping):
        return ()

    result: list[str] = []
    seen: set[str] = set()
    for field in ("preferred", "fallback"):
        values = entry.get(field)
        if not isinstance(values, (list, tuple)):
            continue
        for value in values:
            if type(value) is not str or value in seen:
                continue
            seen.add(value)
            result.append(value)
    return tuple(result)


def canonical_operator_policy(
    configuration: Mapping[str, Any],
) -> dict[str, tuple[tuple[str, str], ...]]:
    """Return canonical ``(model, effort)`` chains in stable order."""
    validated = validate_configuration(configuration)
    raw = validated.get("operator_policy")
    if raw is None:
        return {}
    return {
        role: tuple((entry["model"], entry["effort"]) for entry in raw[role])
        for role in OPERATOR_ROLES
    }


def translate_operator_policy(
    configuration: Mapping[str, Any],
    endpoint_resolution: Mapping[str, Mapping[str, object]],
) -> dict[str, tuple[tuple[str, str, str], ...]]:
    """Translate exact raw policy entries to unique runtime endpoints.

    Matching is deliberately exact on both model and effort. Ambiguous or
    missing runtime identities fail closed instead of guessing an alias.
    """
    canonical = canonical_operator_policy(configuration)
    translated: dict[str, tuple[tuple[str, str, str], ...]] = {}
    for role, entries in canonical.items():
        role_result: list[tuple[str, str, str]] = []
        for model, effort in entries:
            matches = [
                endpoint
                for endpoint, metadata in endpoint_resolution.items()
                if metadata.get("model") == model and metadata.get("effort") == effort
            ]
            if len(matches) != 1:
                raise ConfigurationError(
                    f"operator_policy.{role} identity {model!r}/{effort!r} "
                    f"maps to {len(matches)} runtime endpoints"
                )
            role_result.append((matches[0], model, effort))
        translated[role] = tuple(role_result)
    return translated


__all__ = [
    "ADVISORY_TO_OPERATOR_ROLE",
    "CAPABILITIES",
    "HARD_CONSTRAINTS",
    "MutationResult",
    "OPERATOR_POLICY_FIELDS",
    "OPERATOR_ROLES",
    "OUTCOME_RECOMMENDED",
    "OUTCOME_REJECTED",
    "OUTCOME_UNKNOWN",
    "OUTCOME_UNRESOLVED",
    "PUBLIC_ROLES",
    "ROLE_COVERAGE_THRESHOLD",
    "ROLE_FIELDS",
    "ROLE_WEIGHTS",
    "TIE_BREAK",
    "ConfigurationError",
    "apply_role_selections",
    "canonical_operator_policy",
    "compute_file_sha256",
    "configured_role_identifiers",
    "is_public_role",
    "load_configuration",
    "mutate_configuration_file",
    "translate_operator_policy",
    "validate_configuration",
]