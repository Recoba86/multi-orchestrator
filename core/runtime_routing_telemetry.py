"""Routing Telemetry and Target-Share Reporting (Task 9).

Normative references:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§4, §8)
docs/superpowers/plans/2026-08-26-solmode-grokmode-weighted-routing.md (Task 9)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
from typing import Mapping, Optional, Sequence

from core.model_availability import sanitize_identifier
from core.runtime_routing_policy import RuntimePolicy

__all__ = [
    "TELEMETRY_SCHEMA_VERSION",
    "TELEMETRY_PATH_DEFAULT",
    "RoutingEvent",
    "TargetShareReport",
    "append_routing_event",
    "read_telemetry_events",
    "aggregate_telemetry",
]

TELEMETRY_SCHEMA_VERSION = 1
TELEMETRY_PATH_DEFAULT = Path.home() / ".agents" / "runtime-routing" / "routing-telemetry.jsonl"

_STATE_DIR_MODE = 0o700
_STATE_FILE_MODE = 0o600


@dataclass(frozen=True)
class RoutingEvent:
    """Immutable single-dispatch routing telemetry record."""
    timestamp_utc: str
    mode: str
    role: str
    endpoint_id: str
    endpoint_independence_group: str
    capacity_domain: str
    model: str
    effort: str
    core_validation_status: str
    table_used: str
    mission_id: str
    ordinal: int
    bucket: Optional[int]
    algorithm_version: int
    excluded_unverified: tuple[str, ...]
    implementer_independence_group: Optional[str]
    decision_reason: str
    version: int = TELEMETRY_SCHEMA_VERSION


@dataclass(frozen=True)
class TargetShareReport:
    """Read-only comparison of observed vs permanent target shares."""
    total_permanent_dispatches: int
    total_all_dispatches: int
    domain_shares: dict[str, dict[str, float | int]]
    ox_stats: dict[str, float | int]
    window_hours: Optional[float]
    malformed_rows_count: int


def append_routing_event(event: RoutingEvent, path: Optional[Path] = None) -> None:
    """Append one complete JSONL routing record with privacy and write safety."""
    telemetry_path = TELEMETRY_PATH_DEFAULT if path is None else Path(path)
    parent = telemetry_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    if telemetry_path.is_symlink():
        raise RuntimeError(f"Refusing to write telemetry to symlink: {telemetry_path}")

    # Build sanitized record dict
    payload_dict = {
        "version": event.version,
        "timestamp_utc": sanitize_identifier(event.timestamp_utc),
        "mode": sanitize_identifier(event.mode),
        "role": sanitize_identifier(event.role),
        "endpoint_id": sanitize_identifier(event.endpoint_id),
        "endpoint_independence_group": sanitize_identifier(event.endpoint_independence_group),
        "capacity_domain": sanitize_identifier(event.capacity_domain),
        "model": sanitize_identifier(event.model),
        "effort": sanitize_identifier(event.effort),
        "core_validation_status": sanitize_identifier(event.core_validation_status),
        "table_used": sanitize_identifier(event.table_used),
        "mission_id": sanitize_identifier(event.mission_id),
        "ordinal": event.ordinal,
        "bucket": event.bucket,
        "algorithm_version": event.algorithm_version,
        "excluded_unverified": [sanitize_identifier(x) for x in event.excluded_unverified],
        "implementer_independence_group": sanitize_identifier(event.implementer_independence_group) if event.implementer_independence_group else None,
        "decision_reason": sanitize_identifier(event.decision_reason),
    }

    line = json.dumps(payload_dict, sort_keys=True) + "\n"
    line_bytes = line.encode("utf-8")

    fd = os.open(
        telemetry_path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        _STATE_FILE_MODE,
    )
    try:
        os.write(fd, line_bytes)
    finally:
        os.close(fd)

    try:
        os.chmod(telemetry_path, _STATE_FILE_MODE)
        os.chmod(parent, _STATE_DIR_MODE)
    except OSError:
        pass


def read_telemetry_events(path: Optional[Path] = None) -> tuple[tuple[RoutingEvent, ...], int]:
    """Read all valid JSONL telemetry events from storage; count malformed rows."""
    telemetry_path = TELEMETRY_PATH_DEFAULT if path is None else Path(path)
    if not telemetry_path.is_file() or telemetry_path.is_symlink():
        return (), 0

    events: list[RoutingEvent] = []
    malformed_count = 0

    try:
        with open(telemetry_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if not isinstance(data, dict) or data.get("version") != TELEMETRY_SCHEMA_VERSION:
                        malformed_count += 1
                        continue

                    events.append(
                        RoutingEvent(
                            timestamp_utc=str(data.get("timestamp_utc", "")),
                            mode=str(data.get("mode", "")),
                            role=str(data.get("role", "")),
                            endpoint_id=str(data.get("endpoint_id", "")),
                            endpoint_independence_group=str(data.get("endpoint_independence_group", "")),
                            capacity_domain=str(data.get("capacity_domain", "")),
                            model=str(data.get("model", "")),
                            effort=str(data.get("effort", "")),
                            core_validation_status=str(data.get("core_validation_status", "")),
                            table_used=str(data.get("table_used", "")),
                            mission_id=str(data.get("mission_id", "")),
                            ordinal=int(data.get("ordinal", 0)),
                            bucket=data.get("bucket"),
                            algorithm_version=int(data.get("algorithm_version", 1)),
                            excluded_unverified=tuple(data.get("excluded_unverified", ())),
                            implementer_independence_group=data.get("implementer_independence_group"),
                            decision_reason=str(data.get("decision_reason", "")),
                        )
                    )
                except Exception:
                    malformed_count += 1
    except OSError:
        return (), 0

    return tuple(events), malformed_count


def aggregate_telemetry(
    path: Optional[Path] = None,
    policy: Optional[RuntimePolicy] = None,
    window: Optional[timedelta] = None,
    now: Optional[datetime] = None,
) -> TargetShareReport:
    """Aggregate telemetry records comparing observed shares against policy targets."""
    events, malformed_count = read_telemetry_events(path)
    now_dt = now or datetime.now(timezone.utc)

    filtered_events: list[RoutingEvent] = []
    for ev in events:
        if window is not None:
            try:
                ev_time = datetime.fromisoformat(ev.timestamp_utc.replace("Z", "+00:00"))
                if now_dt - ev_time > window:
                    continue
            except Exception:
                continue
        filtered_events.append(ev)

    total_all = len(filtered_events)

    # Permanent target domains: gemini 45, supergrok 25, gpt_plus 17, cheap 7, opus 6
    permanent_targets = policy.global_targets if policy else {
        "gemini": 45.0,
        "supergrok": 25.0,
        "gpt_plus": 17.0,
        "cheap": 7.0,
        "opus": 6.0,
    }

    permanent_counts = {dom: 0 for dom in permanent_targets}
    ox_count = 0

    for ev in filtered_events:
        dom = ev.capacity_domain
        if dom in permanent_counts:
            permanent_counts[dom] += 1
        elif dom == "ox_combo":
            ox_count += 1

    total_permanent = sum(permanent_counts.values())

    domain_shares: dict[str, dict[str, float | int]] = {}
    for dom, target_pct in permanent_targets.items():
        cnt = permanent_counts[dom]
        obs_pct = (cnt / total_permanent * 100.0) if total_permanent > 0 else 0.0
        delta_pct = obs_pct - target_pct
        domain_shares[dom] = {
            "count": cnt,
            "observed_pct": obs_pct,
            "target_pct": target_pct,
            "delta_pct": delta_pct,
        }

    ox_share_of_all = (ox_count / total_all * 100.0) if total_all > 0 else 0.0
    ox_stats: dict[str, float | int] = {
        "count": ox_count,
        "share_of_all_dispatches_pct": ox_share_of_all,
    }

    return TargetShareReport(
        total_permanent_dispatches=total_permanent,
        total_all_dispatches=total_all,
        domain_shares=domain_shares,
        ox_stats=ox_stats,
        window_hours=window.total_seconds() / 3600.0 if window else None,
        malformed_rows_count=malformed_count,
    )
