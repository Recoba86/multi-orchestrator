"""Runtime failure-domain health and configurable cooldown subsystem (Task 8).

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§3, §5, §10)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 8)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
from typing import Collection, Mapping, Optional

from core.runtime_routing_policy import RuntimePolicy

__all__ = [
    "DEFAULT_COOLDOWN_SECONDS",
    "HEALTH_STATE_PATH_DEFAULT",
    "HEALTH_SCHEMA_VERSION",
    "FailureKind",
    "DomainHealthState",
    "domain_of_endpoint",
    "domain_eligible",
    "excluded_domains",
    "excluded_endpoints",
    "record_failure",
    "clear_health",
    "load_health_state",
]

DEFAULT_COOLDOWN_SECONDS = 1800  # 30 minutes
HEALTH_STATE_PATH_DEFAULT = Path.home() / ".agents" / "runtime-routing" / "health.json"
HEALTH_SCHEMA_VERSION = 1

_STATE_DIR_MODE = 0o700
_STATE_FILE_MODE = 0o600


class FailureKind(str, Enum):
    HTTP_429 = "HTTP_429"
    HTTP_503 = "HTTP_503"
    TIMEOUT = "TIMEOUT"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"


class DomainHealthState(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    COOLDOWN = "COOLDOWN"


@dataclass(frozen=True)
class DomainCooldownRecord:
    cooldown_until: int
    reason: str
    last_failure_at: int


def domain_of_endpoint(policy: RuntimePolicy, endpoint_id: str) -> str:
    """Derive failure domain for an endpoint ID directly from validated policy."""
    for dom_name, domain_obj in policy.domains.items():
        if endpoint_id in domain_obj.endpoint_ids:
            return dom_name
    raise ValueError(f"Endpoint {endpoint_id!r} not found in any failure domain.")


def load_health_state(path: Optional[Path] = None) -> dict[str, DomainCooldownRecord]:
    """Read persisted health state. Strictly read-only and zero mutation."""
    state_path = HEALTH_STATE_PATH_DEFAULT if path is None else Path(path)
    if state_path.is_symlink():
        return {}

    try:
        raw = state_path.read_bytes()
    except (FileNotFoundError, OSError):
        return {}

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict) or data.get("version") != HEALTH_SCHEMA_VERSION:
        return {}

    domains_dict = data.get("domains", {})
    if not isinstance(domains_dict, dict):
        return {}

    records: dict[str, DomainCooldownRecord] = {}
    for dom, item in domains_dict.items():
        if isinstance(item, dict):
            until = item.get("cooldown_until")
            reason = item.get("reason", "unknown")
            last_fail = item.get("last_failure_at", 0)
            if isinstance(until, int) and not isinstance(until, bool):
                records[dom] = DomainCooldownRecord(
                    cooldown_until=until,
                    reason=str(reason),
                    last_failure_at=int(last_fail) if isinstance(last_fail, int) else 0,
                )
    return records


def _write_health_state(records: Mapping[str, DomainCooldownRecord], path: Optional[Path] = None) -> None:
    """Atomic 0600 write of health state."""
    state_path = HEALTH_STATE_PATH_DEFAULT if path is None else Path(path)
    parent = state_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    if state_path.is_symlink():
        raise RuntimeError(f"Refusing to write health state to symlink: {state_path}")

    payload_dict = {
        "version": HEALTH_SCHEMA_VERSION,
        "domains": {
            dom: {
                "cooldown_until": rec.cooldown_until,
                "reason": rec.reason,
                "last_failure_at": rec.last_failure_at,
            }
            for dom, rec in records.items()
        },
    }
    payload = json.dumps(payload_dict, sort_keys=True).encode("utf-8")

    tmp = parent / f".{state_path.name}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _STATE_FILE_MODE)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.chmod(tmp, _STATE_FILE_MODE)
        os.replace(tmp, state_path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    try:
        os.chmod(parent, _STATE_DIR_MODE)
    except OSError:
        pass


def domain_eligible(
    domain: str,
    now: Optional[int] = None,
    path: Optional[Path] = None,
    policy: Optional[RuntimePolicy] = None,
) -> bool:
    """Query whether a failure domain is currently eligible (not in cooldown)."""
    current_time = int(now if now is not None else int(datetime.now().timestamp()))
    records = load_health_state(path)
    if domain not in records:
        return True
    rec = records[domain]
    return current_time >= rec.cooldown_until


def excluded_domains(now: Optional[int] = None, path: Optional[Path] = None) -> tuple[str, ...]:
    """Return all failure domains currently in cooldown."""
    current_time = int(now if now is not None else int(datetime.now().timestamp()))
    records = load_health_state(path)
    unhealthy = [
        dom for dom, rec in records.items()
        if current_time < rec.cooldown_until
    ]
    return tuple(sorted(unhealthy))


def excluded_endpoints(
    policy: RuntimePolicy,
    now: Optional[int] = None,
    path: Optional[Path] = None,
) -> tuple[str, ...]:
    """Return all endpoint IDs suppressed due to active failure-domain cooldowns."""
    unhealthy_doms = set(excluded_domains(now=now, path=path))
    endpoints = []
    for dom in unhealthy_doms:
        if dom in policy.domains:
            endpoints.extend(policy.domains[dom].endpoint_ids)
    return tuple(sorted(set(endpoints)))


def record_failure(
    domain: str,
    failure_kind: FailureKind | str,
    now: Optional[int] = None,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    path: Optional[Path] = None,
    policy: Optional[RuntimePolicy] = None,
) -> None:
    """Record a qualifying capacity/transient failure for a domain and activate cooldown."""
    if policy is not None and domain not in policy.domains:
        raise ValueError(f"Unknown domain {domain!r} not in policy.domains")

    try:
        kind = FailureKind(failure_kind)
    except ValueError as exc:
        raise ValueError(f"Unsupported failure kind {failure_kind!r}") from exc

    if isinstance(cooldown_seconds, bool) or not isinstance(cooldown_seconds, int) or cooldown_seconds <= 0:
        raise ValueError(f"cooldown_seconds must be a positive integer, got {cooldown_seconds!r}")

    current_time = int(now if now is not None else int(datetime.now().timestamp()))
    records = dict(load_health_state(path))

    existing_until = records[domain].cooldown_until if domain in records else 0
    new_until = max(existing_until, current_time + cooldown_seconds)

    records[domain] = DomainCooldownRecord(
        cooldown_until=new_until,
        reason=kind.value,
        last_failure_at=current_time,
    )
    _write_health_state(records, path)


def clear_health(path: Optional[Path] = None) -> None:
    """Reset all failure domain health states to healthy."""
    _write_health_state({}, path)
