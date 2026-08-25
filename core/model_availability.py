"""Read-only model availability and provider health foundation.

This module is descriptive and provider-agnostic.  It never infers provider
identities from model strings, never probes networks or executes commands,
and keeps model availability strictly separate from configured, declared,
or capability metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
import re
from typing import Callable


class ModelStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class ProviderStatus(str, Enum):
    HEALTHY = "HEALTHY"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class Freshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ErrorCategory(str, Enum):
    AUTH = "AUTH"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA = "QUOTA"
    SERVER = "SERVER"
    TIMEOUT = "TIMEOUT"
    NOT_FOUND = "NOT_FOUND"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    PROBE_UNSUPPORTED = "PROBE_UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


MODEL_AVAILABLE = ModelStatus.AVAILABLE.value
MODEL_UNAVAILABLE = ModelStatus.UNAVAILABLE.value
MODEL_UNKNOWN = ModelStatus.UNKNOWN.value

PROVIDER_HEALTHY = ProviderStatus.HEALTHY.value
PROVIDER_UNAVAILABLE = ProviderStatus.UNAVAILABLE.value
PROVIDER_UNKNOWN = ProviderStatus.UNKNOWN.value

FRESHNESS_FRESH = Freshness.FRESH.value
FRESHNESS_STALE = Freshness.STALE.value
FRESHNESS_UNKNOWN = Freshness.UNKNOWN.value

PROBE_UNSUPPORTED = ErrorCategory.PROBE_UNSUPPORTED.value
PROBE_FAILED = "PROBE_FAILED"

PROVENANCE_OFFLINE = "offline-declaration"
PROVENANCE_PROBE = "active-probe"
PROVENANCE_UNSUPPORTED = "probe-unsupported"

_MAX_IDENTIFIER_LEN = 512
_MAX_DISPLAY_IDENTIFIER_LEN = 384
_MAX_DETAIL_LEN = 2048

_CONTROL_OR_ESC_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\x1b]")
_IDENTIFIER_DISALLOWED = re.compile(r"[\r\n\x00-\x1f\x7f-\x9f\x1b]")


def sanitize_identifier(value: str) -> str:
    """Sanitize identifier for safe display without newline/control code injection."""
    if not isinstance(value, str):
        return ""
    cleaned = _IDENTIFIER_DISALLOWED.sub("?", value).replace(chr(92), chr(92) + chr(92))
    if len(cleaned) > _MAX_DISPLAY_IDENTIFIER_LEN:
        return cleaned[: _MAX_DISPLAY_IDENTIFIER_LEN - 3] + "..."
    return cleaned


def _validate_safe_string(value: object, field_name: str, allow_surrounding_space: bool = False) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or not value.strip() or len(value) > _MAX_IDENTIFIER_LEN:
        raise ValueError(f"{field_name} must be a non-empty string <= {_MAX_IDENTIFIER_LEN} chars")
    if not allow_surrounding_space and value != value.strip():
        raise ValueError(f"{field_name} must not contain leading or trailing whitespace")
    if _CONTROL_OR_ESC_RE.search(value):
        raise ValueError(f"{field_name} must not contain control or escape characters")
    return value


def _validate_detail(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("detail must be a string")
    if len(value) > _MAX_DETAIL_LEN:
        raise ValueError(f"detail must be <= {_MAX_DETAIL_LEN} chars")
    if _CONTROL_OR_ESC_RE.search(value):
        raise ValueError("detail must not contain control or escape characters")
    return value


def _validate_latency(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("latency_ms must be a non-negative number")
    num = float(value)
    if math.isnan(num) or math.isinf(num) or num < 0:
        raise ValueError("latency_ms must be a finite, non-negative number")
    return num


@dataclass(frozen=True)
class ModelAvailabilityRecord:
    """Descriptive, point-in-time model availability observation."""

    model_id: str
    provider_id: str
    status: ModelStatus
    provenance: str
    freshness: Freshness = Freshness.UNKNOWN
    checked_at: datetime | None = None
    latency_ms: float | None = None
    error_category: ErrorCategory | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        _validate_safe_string(self.model_id, "model_id", allow_surrounding_space=True)
        _validate_safe_string(self.provider_id, "provider_id", allow_surrounding_space=False)
        _validate_safe_string(self.provenance, "provenance", allow_surrounding_space=False)
        _validate_detail(self.detail)

        if not isinstance(self.status, ModelStatus):
            raise TypeError("status must be a ModelStatus enum member")
        if not isinstance(self.freshness, Freshness):
            raise TypeError("freshness must be a Freshness enum member")
        if self.error_category is not None and not isinstance(self.error_category, ErrorCategory):
            raise TypeError("error_category must be an ErrorCategory enum member or None")

        if self.checked_at is not None:
            if not isinstance(self.checked_at, datetime):
                raise TypeError("checked_at must be a datetime instance or None")
            if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
                raise ValueError("checked_at must be timezone-aware")
            object.__setattr__(self, "checked_at", self.checked_at.astimezone(timezone.utc))

        _validate_latency(self.latency_ms)

        if self.status == ModelStatus.AVAILABLE:
            if self.freshness != Freshness.FRESH:
                raise ValueError("AVAILABLE status requires FRESH freshness")
            if self.checked_at is None:
                raise ValueError("AVAILABLE status requires checked_at timestamp")
            if self.latency_ms is None:
                raise ValueError("AVAILABLE status requires latency_ms measurement")

        if (
            self.provenance in (PROVENANCE_OFFLINE, PROVENANCE_UNSUPPORTED)
            or self.error_category == ErrorCategory.PROBE_UNSUPPORTED
        ):
            if self.status != ModelStatus.UNKNOWN:
                raise ValueError("offline and probe-unsupported records must have UNKNOWN status")
            if self.freshness != Freshness.UNKNOWN:
                raise ValueError("offline and probe-unsupported records must have UNKNOWN freshness")
            if self.checked_at is not None:
                raise ValueError("offline and probe-unsupported records must not have checked_at")
            if self.latency_ms is not None:
                raise ValueError("offline and probe-unsupported records must not have latency_ms")


@dataclass(frozen=True)
class ProviderHealthRecord:
    """Descriptive, point-in-time provider health observation."""

    provider_id: str
    status: ProviderStatus
    provenance: str
    freshness: Freshness = Freshness.UNKNOWN
    checked_at: datetime | None = None
    latency_ms: float | None = None
    error_category: ErrorCategory | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        _validate_safe_string(self.provider_id, "provider_id", allow_surrounding_space=False)
        _validate_safe_string(self.provenance, "provenance", allow_surrounding_space=False)
        _validate_detail(self.detail)

        if not isinstance(self.status, ProviderStatus):
            raise TypeError("status must be a ProviderStatus enum member")
        if not isinstance(self.freshness, Freshness):
            raise TypeError("freshness must be a Freshness enum member")
        if self.error_category is not None and not isinstance(self.error_category, ErrorCategory):
            raise TypeError("error_category must be an ErrorCategory enum member or None")

        if self.checked_at is not None:
            if not isinstance(self.checked_at, datetime):
                raise TypeError("checked_at must be a datetime instance or None")
            if self.checked_at.tzinfo is None or self.checked_at.utcoffset() is None:
                raise ValueError("checked_at must be timezone-aware")
            object.__setattr__(self, "checked_at", self.checked_at.astimezone(timezone.utc))

        _validate_latency(self.latency_ms)

        if self.status == ProviderStatus.HEALTHY:
            if self.freshness != Freshness.FRESH:
                raise ValueError("HEALTHY status requires FRESH freshness")
            if self.checked_at is None:
                raise ValueError("HEALTHY status requires checked_at timestamp")
            if self.latency_ms is None:
                raise ValueError("HEALTHY status requires latency_ms measurement")

        if (
            self.provenance in (PROVENANCE_OFFLINE, PROVENANCE_UNSUPPORTED)
            or self.error_category == ErrorCategory.PROBE_UNSUPPORTED
        ):
            if self.status != ProviderStatus.UNKNOWN:
                raise ValueError("offline and probe-unsupported records must have UNKNOWN status")
            if self.freshness != Freshness.UNKNOWN:
                raise ValueError("offline and probe-unsupported records must have UNKNOWN freshness")
            if self.checked_at is not None:
                raise ValueError("offline and probe-unsupported records must not have checked_at")
            if self.latency_ms is not None:
                raise ValueError("offline and probe-unsupported records must not have latency_ms")


def observe_model_offline(model_id: str, provider_id: str = "UNKNOWN") -> ModelAvailabilityRecord:
    """Observe model availability offline from static context. Always UNKNOWN."""
    return ModelAvailabilityRecord(
        model_id=model_id,
        provider_id=provider_id,
        status=ModelStatus.UNKNOWN,
        provenance=PROVENANCE_OFFLINE,
        freshness=Freshness.UNKNOWN,
        checked_at=None,
        latency_ms=None,
        error_category=None,
        detail="offline observation; no active probe",
    )


def observe_provider_offline(provider_id: str) -> ProviderHealthRecord:
    """Observe provider health offline from static context. Always UNKNOWN."""
    return ProviderHealthRecord(
        provider_id=provider_id,
        status=ProviderStatus.UNKNOWN,
        provenance=PROVENANCE_OFFLINE,
        freshness=Freshness.UNKNOWN,
        checked_at=None,
        latency_ms=None,
        error_category=None,
        detail="offline observation; no active probe",
    )


def validate_timeout(timeout_seconds: float | int) -> float:
    """Validate that timeout is a bounded positive float."""
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise TypeError("timeout must be a positive number")
    val = float(timeout_seconds)
    if math.isnan(val) or math.isinf(val) or val <= 0 or val > 300:
        raise ValueError("timeout must be a finite positive number <= 300s")
    return val


ProbeAdapter = Callable[[str, str, float, str], ModelAvailabilityRecord]


def probe_model_availability(
    model_id: str,
    provider_id: str = "UNKNOWN",
    *,
    timeout_seconds: float = 5.0,
    adapter: ProbeAdapter | None = None,
) -> ModelAvailabilityRecord:
    """Probe model availability.

    With no adapter, executes zero network operations and returns UNKNOWN/PROBE_UNSUPPORTED.
    When a pure test adapter is injected, only explicit ids, bounded timeout, and a fixed empty
    payload marker are passed.
    """
    valid_timeout = validate_timeout(timeout_seconds)
    if adapter is None:
        return ModelAvailabilityRecord(
            model_id=model_id,
            provider_id=provider_id,
            status=ModelStatus.UNKNOWN,
            provenance=PROVENANCE_UNSUPPORTED,
            freshness=Freshness.UNKNOWN,
            checked_at=None,
            latency_ms=None,
            error_category=ErrorCategory.PROBE_UNSUPPORTED,
            detail="no supported active probe adapter; network operations unavailable",
        )
    # ponytail: pure injectable test seam only; passes minimal parameters
    res = adapter(model_id, provider_id, valid_timeout, "EMPTY_PROBE_PAYLOAD")
    if not isinstance(res, ModelAvailabilityRecord):
        raise TypeError("adapter must return a ModelAvailabilityRecord")
    if res.model_id != model_id:
        raise ValueError(f"adapter returned mismatched model_id: expected {model_id!r}, got {res.model_id!r}")
    if res.provider_id != provider_id:
        raise ValueError(f"adapter returned mismatched provider_id: expected {provider_id!r}, got {res.provider_id!r}")
    return res


def probe_provider_health(
    provider_id: str,
    *,
    timeout_seconds: float = 5.0,
    adapter: Callable[[str, float, str], ProviderHealthRecord] | None = None,
) -> ProviderHealthRecord:
    """Probe provider health.

    With no adapter, executes zero network operations and returns UNKNOWN/PROBE_UNSUPPORTED.
    """
    valid_timeout = validate_timeout(timeout_seconds)
    if adapter is None:
        return ProviderHealthRecord(
            provider_id=provider_id,
            status=ProviderStatus.UNKNOWN,
            provenance=PROVENANCE_UNSUPPORTED,
            freshness=Freshness.UNKNOWN,
            checked_at=None,
            latency_ms=None,
            error_category=ErrorCategory.PROBE_UNSUPPORTED,
            detail="no supported active probe adapter; network operations unavailable",
        )
    res = adapter(provider_id, valid_timeout, "EMPTY_PROBE_PAYLOAD")
    if not isinstance(res, ProviderHealthRecord):
        raise TypeError("adapter must return a ProviderHealthRecord")
    if res.provider_id != provider_id:
        raise ValueError(f"adapter returned mismatched provider_id: expected {provider_id!r}, got {res.provider_id!r}")
    return res
