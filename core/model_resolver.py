"""Provider-agnostic, read-only, deterministic resolver for the logical roles.

The resolver combines existing structures (declarative configuration, local
declaration discovery, availability records, built-in capability metadata, and
offline intelligence profiles) into one deterministic, evidence-bearing
recommendation. It never mutates state, probes a provider, or reaches the Host.

Hard constraints are evaluated before any advisory ranking:

1. ``exact_configured_identity``: only exact raw identifiers from a role's
   ``preferred``/``fallback`` lists are candidates.
2. ``discovered_identity``: a candidate must appear as an exact raw identity in
   at least one available discovery source.
3. ``availability_not_unavailable``: an explicit ``UNAVAILABLE`` observation
   rejects the candidate.

After those gates, advisory evidence is evaluated. ``UNKNOWN`` availability is
never treated as ``AVAILABLE`` or ``HEALTHY``; it produces an ``UNRESOLVED``
outcome. Capability metadata and intelligence profiles are advisory. Only a
candidate that is discovered, explicitly ``AVAILABLE``, capability-compatible,
and backed by an ``ACTIVE`` intelligence profile with sufficient coverage is
``RECOMMENDED``. Recommendations tie-break by weighted score descending,
coverage descending, confidence descending, then exact raw identity ascending.

Per-model availability is an optional input (``availability``). When omitted,
the resolver observes every candidate offline as ``UNKNOWN``, so it never
fabricates availability. Personal/private endpoints are therefore optional and
never required.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from core import model_intelligence
from core.model_availability import (
    ModelAvailabilityRecord,
    ModelStatus,
    observe_model_offline,
)
from core.model_capabilities import (
    STATUS_COMPATIBLE,
    STATUS_INCOMPATIBLE,
    STATUS_KNOWN,
    STATUS_UNKNOWN,
    assess_role_compatibility,
    capability_hints_for_role,
    lookup_model_capabilities,
)
from core.model_discovery import DiscoveryResult
from core.model_policy import (
    OUTCOME_RECOMMENDED,
    OUTCOME_REJECTED,
    OUTCOME_UNKNOWN,
    OUTCOME_UNRESOLVED,
    configured_role_identifiers,
    is_public_role,
)


@dataclass(frozen=True)
class ResolutionEvidence:
    """Separate evidence dimensions, none of which imply another."""

    status: str | None = None
    confidence: float | None = None
    freshness: str | None = None
    provenance: str | None = None
    checked_at: datetime | None = None
    latency_ms: float | None = None


@dataclass(frozen=True)
class ResolutionOutcome:
    """One candidate's outcome with its explicit evidence and reason."""

    raw_identity: str
    outcome: str
    reason: str
    evidence: ResolutionEvidence = ResolutionEvidence()
    weighted_score: float | None = None
    coverage: float | None = None

    @property
    def recommended(self) -> bool:
        return self.outcome == OUTCOME_RECOMMENDED


@dataclass(frozen=True)
class RoleResolution:
    """Deterministic result for one logical role."""

    role: str
    candidates: tuple[ResolutionOutcome, ...]
    recommendations: tuple[ResolutionOutcome, ...]

    @property
    def outcome(self) -> str:
        if self.recommendations:
            return OUTCOME_RECOMMENDED
        if any(item.outcome == OUTCOME_UNRESOLVED for item in self.candidates):
            return OUTCOME_UNRESOLVED
        if self.candidates and all(
            item.outcome == OUTCOME_REJECTED for item in self.candidates
        ):
            return OUTCOME_REJECTED
        return OUTCOME_UNKNOWN

    @property
    def resolved_model(self) -> str | None:
        if not self.recommendations:
            return None
        return self.recommendations[0].raw_identity


def _discovered_identities(discovery: Iterable[DiscoveryResult]) -> tuple[str, ...]:
    identities: list[str] = []
    seen: set[str] = set()
    for result in discovery:
        if not isinstance(result, DiscoveryResult) or not result.available:
            continue
        for model in result.models:
            if model not in seen:
                seen.add(model)
                identities.append(model)
    return tuple(identities)


def _evidence(record: ModelAvailabilityRecord, confidence: float | None) -> ResolutionEvidence:
    return ResolutionEvidence(
        status=record.status.value,
        freshness=record.freshness.value,
        provenance=record.provenance,
        checked_at=record.checked_at,
        latency_ms=record.latency_ms,
        confidence=confidence,
    )


def _outcome(
    identity: str,
    outcome: str,
    reason: str,
    record: ModelAvailabilityRecord,
    weighted_score: float | None,
    coverage: float | None,
    *,
    confidence: float | None = None,
) -> ResolutionOutcome:
    return ResolutionOutcome(
        raw_identity=identity,
        outcome=outcome,
        reason=reason,
        evidence=_evidence(record, confidence),
        weighted_score=weighted_score,
        coverage=coverage,
    )


def _classify(
    identity: str,
    discovered: set[str],
    record: ModelAvailabilityRecord,
    hints: tuple[str, ...],
    recommendation_by_identity: Mapping[str, model_intelligence.RoleRecommendation],
) -> ResolutionOutcome:
    if identity not in discovered:
        return _outcome(identity, OUTCOME_REJECTED, "not-discovered", record, None, None)
    if record.status == ModelStatus.UNAVAILABLE:
        return _outcome(identity, OUTCOME_REJECTED, "unavailable", record, None, None)
    if record.status == ModelStatus.UNKNOWN:
        return _outcome(
            identity, OUTCOME_UNRESOLVED, "availability-unknown", record, None, None
        )

    metadata = lookup_model_capabilities(identity)
    if metadata.status != STATUS_KNOWN:
        return _outcome(
            identity, OUTCOME_UNRESOLVED, "metadata-unavailable", record, None, None
        )

    compatibility = assess_role_compatibility(identity, hints)
    if compatibility.status == STATUS_INCOMPATIBLE:
        return _outcome(
            identity, OUTCOME_UNRESOLVED, "capability-incompatible", record, None, None
        )
    if compatibility.status != STATUS_COMPATIBLE:
        return _outcome(
            identity,
            OUTCOME_UNRESOLVED,
            "unknown-capability-hint",
            record,
            None,
            None,
        )

    recommendation = recommendation_by_identity.get(identity)
    if recommendation is None:
        return _outcome(
            identity,
            OUTCOME_UNRESOLVED,
            "insufficient-intelligence-evidence",
            record,
            None,
            None,
        )
    return _outcome(
        identity,
        OUTCOME_RECOMMENDED,
        "recommended",
        record,
        recommendation.weighted_score,
        recommendation.coverage,
        confidence=recommendation.confidence,
    )


def resolve_role(
    configuration: Mapping[str, Mapping[str, object]],
    role: str,
    *,
    discovery: Iterable[DiscoveryResult] = (),
    availability: Mapping[str, ModelAvailabilityRecord] | None = None,
    profiles: Mapping[object, model_intelligence.ModelProfile]
    | Iterable[model_intelligence.ModelProfile] = (),
) -> RoleResolution:
    """Resolve one logical role without mutation or network access."""
    if not is_public_role(role):
        raise ValueError(f"unknown public role: {role!r}")

    identities = configured_role_identifiers(configuration, role)
    if not identities:
        return RoleResolution(role, (), ())

    discovered = set(_discovered_identities(discovery))
    availability_map = dict(availability) if availability is not None else {}
    hints = capability_hints_for_role(configuration, role)

    profile_values = profiles.values() if isinstance(profiles, Mapping) else profiles
    ranked = model_intelligence.recommend_roles(profile_values, role)
    recommendation_by_identity = {
        recommendation.raw_identity: recommendation for recommendation in ranked
    }

    candidates: list[ResolutionOutcome] = []
    for identity in identities:
        record = (
            availability_map[identity]
            if identity in availability_map
            else observe_model_offline(identity)
        )
        if not isinstance(record, ModelAvailabilityRecord):
            raise TypeError("availability values must be ModelAvailabilityRecord")
        candidates.append(
            _classify(identity, discovered, record, hints, recommendation_by_identity)
        )

    recommendations = tuple(
        sorted(
            (item for item in candidates if item.recommended),
            key=lambda item: (
                -(item.weighted_score if item.weighted_score is not None else 0.0),
                -(item.coverage if item.coverage is not None else 0.0),
                -(
                    item.evidence.confidence
                    if item.evidence.confidence is not None
                    else 0.0
                ),
                item.raw_identity,
            ),
        )
    )
    return RoleResolution(role, tuple(candidates), recommendations)


__all__ = [
    "ResolutionEvidence",
    "ResolutionOutcome",
    "RoleResolution",
    "resolve_role",
]
