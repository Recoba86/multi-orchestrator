"""Offline model identity, evidence, freshness, and advisory ranking.

This module is deliberately descriptive.  It never resolves an alias, probes a
provider, changes configuration, or touches the active runtime.  ``raw`` model
identity is retained for every decision; ``normalized`` is only a deterministic
presentation key and is never used to merge aliases.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from pathlib import Path
from types import MappingProxyType
import unicodedata
from urllib.parse import urlparse

import yaml


STATUS_ACTIVE = "ACTIVE"
STATUS_STALE = "STALE"
STATUS_CONFLICTED = "CONFLICTED"
STATUS_UNKNOWN = "UNKNOWN"
STATUSES = frozenset(
    {STATUS_ACTIVE, STATUS_STALE, STATUS_CONFLICTED, STATUS_UNKNOWN}
)

SCORE_MIN = 0
SCORE_MAX = 10
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0

EVIDENCE_STRENGTH_LOW = "LOW"
EVIDENCE_STRENGTH_MEDIUM = "MEDIUM"
EVIDENCE_STRENGTH_HIGH = "HIGH"
EVIDENCE_STRENGTHS = frozenset(
    {
        EVIDENCE_STRENGTH_LOW,
        EVIDENCE_STRENGTH_MEDIUM,
        EVIDENCE_STRENGTH_HIGH,
    }
)

CONFIDENCE_LOW = "LOW"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_CATEGORIES = frozenset(
    {CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_HIGH}
)
# These are fixed advisory arithmetic values.  The category remains visible on
# each claim; the number is only used for deterministic ranking.
CONFIDENCE_CATEGORY_VALUES = MappingProxyType(
    {
        CONFIDENCE_LOW: 0.25,
        CONFIDENCE_MEDIUM: 0.50,
        CONFIDENCE_HIGH: 0.90,
    }
)
CONFIDENCE_VALUES = CONFIDENCE_CATEGORY_VALUES

CACHE_SCHEMA_VERSION = 1
MIN_ROLE_COVERAGE = 0.50
ROLE_COVERAGE_THRESHOLD = MIN_ROLE_COVERAGE


def _fixed_weights(**values: float) -> MappingProxyType:
    return MappingProxyType({key: float(value) for key, value in values.items()})


# These are advisory, fixed weights.  They do not select a provider or alter a
# request route.  Keeping the table immutable makes ranking reproducible.
ROLE_RECOMMENDATION_WEIGHTS = MappingProxyType(
    {
        "planner": _fixed_weights(
            reasoning=0.40, analysis=0.25, long_context=0.20, coding=0.15
        ),
        "scout": _fixed_weights(
            fast=0.40, analysis=0.30, cost_effective=0.20, reasoning=0.10
        ),
        "worker": _fixed_weights(
            coding=0.40, reasoning=0.30, fast=0.20, long_context=0.10
        ),
        "reviewer": _fixed_weights(
            review=0.40, analysis=0.30, reasoning=0.20, long_context=0.10
        ),
    }
)
ROLE_WEIGHTS = ROLE_RECOMMENDATION_WEIGHTS


def _text(value: object, label: str, *, maximum: int | None = None) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError(f"{label} must not contain control line breaks")
    if maximum is not None and len(value) > maximum:
        raise ValueError(f"{label} is too long")
    return value


def _identifier(value: object, label: str) -> str:
    result = _text(value, label, maximum=256)
    if result != result.strip():
        raise ValueError(f"{label} must not have surrounding whitespace")
    return result


def normalize_identity(raw: str) -> str:
    """Return only deterministic lexical normalization; never resolve aliases."""
    value = _text(raw, "raw identity")
    return unicodedata.normalize("NFKC", value).strip()


def _timestamp(value: datetime | str, label: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif type(value) is str:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            result = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    else:
        raise ValueError(f"{label} must be an aware datetime or ISO-8601 string")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return result.astimezone(timezone.utc)


def _finite(value: object, low: float, high: float, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < low or number > high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}")
    return number


def _score(value: object) -> int:
    if type(value) is not int or not SCORE_MIN <= value <= SCORE_MAX:
        raise ValueError("score must be an integer between 0 and 10")
    return value


def _category(value: object, allowed: frozenset[str], label: str) -> str:
    if type(value) is not str or value not in allowed:
        raise ValueError(f"{label} must be one of {sorted(allowed)!r}")
    return value


def _validate_locator(value: object) -> str:
    locator = _text(value, "evidence locator", maximum=2048)
    parsed = urlparse(locator)
    if not parsed.scheme:
        return locator
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https", "urn"}:
        raise ValueError("evidence locator uses an unsupported scheme")
    if scheme in {"http", "https"} and not parsed.netloc:
        raise ValueError("http evidence locator must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("evidence locator must not contain credentials")
    # Locators are provenance labels only.  No code in this module dereferences them.
    return locator


@dataclass(frozen=True)
class ModelIdentity:
    """Exact raw model identity plus a non-authoritative lexical key."""

    raw: str
    normalized: str = field(init=False)

    def __post_init__(self) -> None:
        _text(self.raw, "raw identity")
        object.__setattr__(self, "normalized", normalize_identity(self.raw))

    @property
    def raw_identity(self) -> str:
        return self.raw

    @property
    def normalized_identity(self) -> str:
        return self.normalized

    @property
    def model(self) -> str:
        return self.raw


@dataclass(frozen=True)
class EvidenceRecord:
    """One provenance record.  Its locator is inert metadata, never a fetch target."""

    id: str
    source_type: str
    strength: str
    locator: str
    observed_at: datetime | str
    summary: str
    expires_at: datetime | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _identifier(self.id, "evidence id"))
        object.__setattr__(
            self, "source_type", _text(self.source_type, "evidence source_type", maximum=128)
        )
        object.__setattr__(
            self,
            "strength",
            _category(self.strength, EVIDENCE_STRENGTHS, "evidence strength"),
        )
        object.__setattr__(self, "locator", _validate_locator(self.locator))
        observed = _timestamp(self.observed_at, "observed_at")
        expires = (
            None
            if self.expires_at is None
            else _timestamp(self.expires_at, "expires_at")
        )
        if expires is not None and expires < observed:
            raise ValueError("expires_at must not precede observed_at")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self, "summary", _text(self.summary, "evidence summary", maximum=500)
        )

    @property
    def evidence_id(self) -> str:
        return self.id

    @property
    def evidence_strength(self) -> str:
        return self.strength

    @property
    def source(self) -> str:
        return self.source_type

    @property
    def provenance(self) -> str:
        return self.source_type

    @property
    def url(self) -> str:
        return self.locator

    def freshness(self, as_of: datetime | str) -> str:
        moment = _timestamp(as_of, "as_of")
        if self.observed_at > moment:
            return STATUS_UNKNOWN
        if self.expires_at is not None and moment >= self.expires_at:
            return STATUS_STALE
        return STATUS_ACTIVE


@dataclass(frozen=True, init=False)
class CapabilityClaim:
    """A scored capability whose provenance evidence is mandatory."""

    capability: str
    score: int
    confidence: str
    evidence: tuple[EvidenceRecord, ...]
    evidence_ids: tuple[str, ...]

    def __init__(
        self,
        capability: str,
        score: int,
        confidence: str,
        evidence: Iterable[EvidenceRecord | str] | EvidenceRecord | str = (),
        *,
        evidence_ids: Iterable[str] | str | None = None,
    ) -> None:
        capability_value = _text(capability, "capability", maximum=128)
        score_value = _score(score)
        confidence_value = _category(
            confidence, CONFIDENCE_CATEGORIES, "confidence category"
        )

        if isinstance(evidence, EvidenceRecord):
            raw_evidence: tuple[EvidenceRecord | str, ...] = (evidence,)
        elif type(evidence) is str:
            raw_evidence = (evidence,)
        else:
            try:
                raw_evidence = tuple(evidence)
            except TypeError as exc:
                raise ValueError("evidence must be a non-empty iterable") from exc

        records: tuple[EvidenceRecord, ...]
        ids: tuple[str, ...]
        if raw_evidence and all(isinstance(item, EvidenceRecord) for item in raw_evidence):
            records = tuple(raw_evidence)  # type: ignore[arg-type]
            ids = tuple(item.id for item in records)
        elif raw_evidence and all(type(item) is str for item in raw_evidence):
            records = ()
            ids = tuple(_identifier(item, "evidence id") for item in raw_evidence)
        elif raw_evidence:
            raise ValueError("evidence must contain only EvidenceRecord or ids")
        else:
            records = ()
            ids = ()

        if evidence_ids is not None:
            if type(evidence_ids) is str:
                referenced = (_identifier(evidence_ids, "evidence id"),)
            else:
                try:
                    referenced = tuple(
                        _identifier(item, "evidence id") for item in evidence_ids
                    )
                except TypeError as exc:
                    raise ValueError("evidence_ids must be a list of ids") from exc
            if ids and ids != referenced:
                raise ValueError("evidence and evidence_ids must match")
            ids = referenced

        if not ids:
            raise ValueError("each capability claim requires evidence ids")
        if len(ids) != len(set(ids)):
            raise ValueError("capability claim evidence ids must be unique")

        object.__setattr__(self, "capability", capability_value)
        object.__setattr__(self, "score", score_value)
        object.__setattr__(self, "confidence", confidence_value)
        object.__setattr__(self, "evidence", records)
        object.__setattr__(self, "evidence_ids", ids)

    @property
    def provenance(self) -> tuple[EvidenceRecord, ...]:
        return self.evidence

    @property
    def confidence_value(self) -> float:
        return CONFIDENCE_CATEGORY_VALUES[self.confidence]

    @property
    def confidence_score(self) -> float:
        return self.confidence_value

    @property
    def confidence_category(self) -> str:
        return self.confidence

    @property
    def numeric_confidence(self) -> float:
        return self.confidence_value


@dataclass(frozen=True)
class ModelProfile:
    """Immutable structured profile assembled from explicit evidence."""

    identity: ModelIdentity
    claims: Mapping[str, CapabilityClaim]
    status: str
    as_of: datetime
    conflicts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ModelIdentity):
            raise ValueError("identity must be a ModelIdentity")
        if self.status not in STATUSES:
            raise ValueError(f"unknown profile status: {self.status!r}")
        if not isinstance(self.claims, Mapping):
            raise ValueError("claims must be a mapping")
        normalized_claims: dict[str, CapabilityClaim] = {}
        for capability, value in self.claims.items():
            if type(capability) is not str or not capability:
                raise ValueError("claim keys must be non-empty strings")
            if not isinstance(value, CapabilityClaim) or value.capability != capability:
                raise ValueError("claim key and capability must match")
            normalized_claims[capability] = value
        object.__setattr__(self, "claims", MappingProxyType(normalized_claims))
        object.__setattr__(self, "as_of", _timestamp(self.as_of, "as_of"))
        object.__setattr__(self, "conflicts", tuple(sorted(set(self.conflicts))))

    @property
    def raw_identity(self) -> str:
        return self.identity.raw

    @property
    def normalized_identity(self) -> str:
        return self.identity.normalized

    @property
    def capabilities(self) -> Mapping[str, CapabilityClaim]:
        return self.claims

    @property
    def freshness(self) -> str:
        return self.status


@dataclass(frozen=True)
class RoleRecommendation:
    """Advisory ranking result; it never authorizes or performs allocation."""

    role: str
    identity: ModelIdentity
    weighted_score: float
    coverage: float
    confidence: float
    status: str = STATUS_ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _text(self.role, "role"))
        if not isinstance(self.identity, ModelIdentity):
            raise ValueError("identity must be a ModelIdentity")
        object.__setattr__(
            self,
            "weighted_score",
            _finite(self.weighted_score, float(SCORE_MIN), float(SCORE_MAX), "weighted_score"),
        )
        object.__setattr__(
            self, "coverage", _finite(self.coverage, 0.0, 1.0, "coverage")
        )
        object.__setattr__(
            self, "confidence", _finite(self.confidence, 0.0, 1.0, "confidence")
        )
        if self.status not in STATUSES:
            raise ValueError(f"unknown recommendation status: {self.status!r}")

    @property
    def model(self) -> str:
        return self.identity.raw

    @property
    def score(self) -> float:
        return self.weighted_score

    @property
    def raw_identity(self) -> str:
        return self.identity.raw


def _claim_groups(
    claims: Mapping[str, CapabilityClaim] | Iterable[CapabilityClaim],
) -> dict[str, list[CapabilityClaim]]:
    if isinstance(claims, Mapping):
        items = []
        for key, value in claims.items():
            if type(key) is not str or not key:
                raise ValueError("claim keys must be non-empty strings")
            if not isinstance(value, CapabilityClaim) or value.capability != key:
                raise ValueError("claim key and capability must match")
            items.append(value)
    else:
        try:
            items = list(claims)
        except TypeError as exc:
            raise ValueError("claims must be a mapping or iterable") from exc
        if any(not isinstance(item, CapabilityClaim) for item in items):
            raise ValueError("claims must contain CapabilityClaim values")
    grouped: dict[str, list[CapabilityClaim]] = {}
    for item in items:
        grouped.setdefault(item.capability, []).append(item)
    return grouped


def _merge_claims(values: list[CapabilityClaim]) -> CapabilityClaim | None:
    first = values[0]
    if any(
        item.score != first.score or item.confidence != first.confidence
        for item in values[1:]
    ):
        return None
    records: list[EvidenceRecord] = []
    ids: list[str] = []
    for item in values:
        for record in item.evidence:
            if record.id not in ids:
                ids.append(record.id)
                records.append(record)
        for evidence_id in item.evidence_ids:
            if evidence_id not in ids:
                ids.append(evidence_id)
    return CapabilityClaim(
        first.capability,
        first.score,
        first.confidence,
        evidence=tuple(records) if records else tuple(ids),
        evidence_ids=tuple(ids),
    )


def build_profile(
    identity: ModelIdentity | str,
    claims: Mapping[str, CapabilityClaim] | Iterable[CapabilityClaim],
    *,
    as_of: datetime | str,
) -> ModelProfile:
    """Build one immutable profile using only the supplied timestamp."""
    model_identity = identity if isinstance(identity, ModelIdentity) else ModelIdentity(identity)
    grouped = _claim_groups(claims)
    merged: dict[str, CapabilityClaim] = {}
    conflicts: list[str] = []
    freshnesses: list[str] = []
    for capability, values in grouped.items():
        claim_value = _merge_claims(values)
        if claim_value is None:
            conflicts.append(capability)
            continue
        merged[capability] = claim_value
        if not claim_value.evidence:
            freshnesses.append(STATUS_UNKNOWN)
        else:
            freshnesses.extend(record.freshness(as_of) for record in claim_value.evidence)

    if conflicts:
        status = STATUS_CONFLICTED
    elif not freshnesses or STATUS_UNKNOWN in freshnesses:
        status = STATUS_UNKNOWN
    elif STATUS_STALE in freshnesses:
        status = STATUS_STALE
    else:
        status = STATUS_ACTIVE
    return ModelProfile(
        identity=model_identity,
        claims=merged,
        status=status,
        as_of=_timestamp(as_of, "as_of"),
        conflicts=tuple(conflicts),
    )


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _entries(value: object, label: str) -> tuple[Mapping[object, object], ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list")
    result = tuple(value)
    if any(not isinstance(item, Mapping) for item in result):
        raise ValueError(f"{label} entries must be mappings")
    return result  # type: ignore[return-value]


def _require_fields(
    value: Mapping[object, object], required: tuple[str, ...], label: str
) -> None:
    for key in required:
        if key not in value:
            raise ValueError(f"{label} requires {key}")


def _validate_cache_shape(cache: Mapping[str, object]) -> None:
    version = cache.get("schema_version")
    if type(version) is not int or version != CACHE_SCHEMA_VERSION:
        raise ValueError("model intelligence cache schema_version must be exactly 1")
    _require_fields(cache, ("schema_version", "evidence", "models"), "cache")
    evidence_entries = _entries(cache.get("evidence"), "cache evidence")
    model_entries = _entries(cache.get("models"), "cache models")
    for item in evidence_entries:
        _require_fields(
            item,
            ("id", "source_type", "strength", "locator", "observed_at", "summary"),
            "evidence entry",
        )
    for item in model_entries:
        _require_fields(item, ("identity", "claims"), "model entry")
        for claim in _entries(item.get("claims"), "model claims"):
            _require_fields(
                claim,
                ("capability", "score", "confidence", "evidence_ids"),
                "claim entry",
            )
            ids = claim.get("evidence_ids")
            if not isinstance(ids, (list, tuple)) or not ids:
                raise ValueError("claim evidence_ids must be a non-empty list")


def _record_from_cache(item: Mapping[object, object]) -> EvidenceRecord:
    return EvidenceRecord(
        id=item["id"],
        source_type=item["source_type"],
        strength=item["strength"],
        locator=item["locator"],
        observed_at=item["observed_at"],
        expires_at=item.get("expires_at"),
        summary=item["summary"],
    )


def _registry_from_cache(cache: Mapping[str, object]) -> dict[str, EvidenceRecord]:
    registry: dict[str, EvidenceRecord] = {}
    for item in _entries(cache.get("evidence"), "cache evidence"):
        record = _record_from_cache(item)
        if record.id in registry:
            raise ValueError(f"duplicate evidence id: {record.id!r}")
        registry[record.id] = record
    return registry


def _claims_from_cache(
    value: object, registry: Mapping[str, EvidenceRecord]
) -> list[CapabilityClaim]:
    result: list[CapabilityClaim] = []
    for item in _entries(value, "model claims"):
        raw_ids = item["evidence_ids"]
        if not isinstance(raw_ids, (list, tuple)) or not raw_ids:
            raise ValueError("claim evidence_ids must be a non-empty list")
        ids = tuple(_identifier(evidence_id, "evidence id") for evidence_id in raw_ids)
        if len(ids) != len(set(ids)):
            raise ValueError("claim evidence_ids must be unique")
        missing = [evidence_id for evidence_id in ids if evidence_id not in registry]
        if missing:
            raise ValueError(f"claim references unknown evidence id: {missing[0]!r}")
        result.append(
            CapabilityClaim(
                capability=item["capability"],
                score=item["score"],
                confidence=item["confidence"],
                evidence=tuple(registry[evidence_id] for evidence_id in ids),
            )
        )
    return result


def load_intelligence_cache(path: str | Path) -> Mapping[str, object]:
    """Read one caller-selected YAML cache with ``safe_load`` only."""
    cache_path = Path(path).expanduser()
    try:
        with cache_path.open("r", encoding="utf-8") as source:
            loaded = yaml.safe_load(source)
    except FileNotFoundError as exc:
        raise ValueError("model intelligence cache not found") from exc
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("model intelligence cache could not be read") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError("model intelligence cache root must be a mapping")
    _validate_cache_shape(loaded)
    frozen = _freeze(loaded)
    if not isinstance(frozen, Mapping):  # pragma: no cover - guarded above
        raise ValueError("model intelligence cache root must be a mapping")
    return frozen


def profiles_from_cache(
    cache: Mapping[str, object], *, as_of: datetime | str
) -> tuple[ModelProfile, ...]:
    """Convert a strict v1 registry cache into immutable profiles."""
    if not isinstance(cache, Mapping):
        raise ValueError("cache must be a mapping")
    _validate_cache_shape(cache)
    registry = _registry_from_cache(cache)
    profiles: list[ModelProfile] = []
    identities: set[str] = set()
    for item in _entries(cache.get("models"), "cache models"):
        raw_identity = item["identity"]
        if type(raw_identity) is not str or not raw_identity.strip():
            raise ValueError("model identity must be a non-empty string")
        if raw_identity in identities:
            raise ValueError(f"duplicate exact model identity: {raw_identity!r}")
        identities.add(raw_identity)
        profiles.append(
            build_profile(
                raw_identity,
                _claims_from_cache(item["claims"], registry),
                as_of=as_of,
            )
        )
    return tuple(profiles)


def recommend_roles(
    profiles: Mapping[object, ModelProfile] | Iterable[ModelProfile],
    role: str,
    *,
    limit: int | None = None,
) -> tuple[RoleRecommendation, ...]:
    """Rank active profiles for one role using fixed advisory weights."""
    if role not in ROLE_RECOMMENDATION_WEIGHTS:
        raise ValueError(f"unknown role: {role!r}")
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("limit must be a non-negative integer")
    values = profiles.values() if isinstance(profiles, Mapping) else profiles
    weights = ROLE_RECOMMENDATION_WEIGHTS[role]
    total_weight = sum(weights.values())
    recommendations: list[RoleRecommendation] = []
    for profile in values:
        if not isinstance(profile, ModelProfile) or profile.status != STATUS_ACTIVE:
            continue
        covered = [capability for capability in weights if capability in profile.claims]
        if not covered:
            continue
        covered_weight = sum(weights[capability] for capability in covered)
        coverage = covered_weight / total_weight
        if coverage < MIN_ROLE_COVERAGE:
            continue
        score = sum(
            weights[capability] * profile.claims[capability].score
            for capability in covered
        )
        confidence = sum(
            weights[capability] * profile.claims[capability].confidence_value
            for capability in covered
        ) / covered_weight
        recommendations.append(
            RoleRecommendation(
                role=role,
                identity=profile.identity,
                weighted_score=score / total_weight,
                coverage=coverage,
                confidence=confidence,
            )
        )
    recommendations.sort(
        key=lambda item: (
            -item.weighted_score,
            -item.coverage,
            -item.confidence,
            item.identity.raw,
        )
    )
    return tuple(recommendations if limit is None else recommendations[:limit])


recommend_role = recommend_roles
load_model_intelligence_cache = load_intelligence_cache


__all__ = [
    "CACHE_SCHEMA_VERSION",
    "CONFIDENCE_CATEGORIES",
    "CONFIDENCE_CATEGORY_VALUES",
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MAX",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_MIN",
    "CONFIDENCE_VALUES",
    "CapabilityClaim",
    "EVIDENCE_STRENGTHS",
    "EVIDENCE_STRENGTH_HIGH",
    "EVIDENCE_STRENGTH_LOW",
    "EVIDENCE_STRENGTH_MEDIUM",
    "EvidenceRecord",
    "MIN_ROLE_COVERAGE",
    "ROLE_COVERAGE_THRESHOLD",
    "ModelIdentity",
    "ModelProfile",
    "ROLE_RECOMMENDATION_WEIGHTS",
    "ROLE_WEIGHTS",
    "RoleRecommendation",
    "SCORE_MAX",
    "SCORE_MIN",
    "STATUSES",
    "STATUS_ACTIVE",
    "STATUS_CONFLICTED",
    "STATUS_STALE",
    "STATUS_UNKNOWN",
    "build_profile",
    "load_intelligence_cache",
    "load_model_intelligence_cache",
    "normalize_identity",
    "profiles_from_cache",
    "recommend_role",
    "recommend_roles",
]
