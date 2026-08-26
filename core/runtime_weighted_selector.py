"""Pure deterministic weighted selector for SolMode/GrokMode routing (Task 3 / 3R integer-exact).

Normative reference:
docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md (§6)
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
from typing import Collection, Iterable, Sequence

from core.runtime_routing_mode import RoutingMode
from core.runtime_routing_policy import CandidateWeight, RuntimePolicy

__all__ = [
    "ALGORITHM_VERSION",
    "DOMAIN_SEPARATOR",
    "NoEligibleCandidateError",
    "SelectionEvidence",
    "SelectionKey",
    "select_candidate",
    "weighted_select",
]

ALGORITHM_VERSION = 1
DOMAIN_SEPARATOR = "multi-orchestrator/runtime-weighted-selector/v1"


class NoEligibleCandidateError(RuntimeError):
    """Raised when candidate filtering leaves zero eligible candidates."""
    pass


@dataclass(frozen=True)
class SelectionKey:
    """Canonical deterministic selection key."""
    mission_id: str
    role: str
    ordinal: int
    mode: RoutingMode

    def __post_init__(self) -> None:
        if not isinstance(self.mission_id, str) or not self.mission_id:
            raise ValueError(f"mission_id must be a non-empty string, got {self.mission_id!r}")
        if not isinstance(self.role, str) or not self.role:
            raise ValueError(f"role must be a non-empty string, got {self.role!r}")
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise ValueError(f"ordinal must be a non-negative integer, got {self.ordinal!r}")
        if not isinstance(self.mode, RoutingMode):
            raise ValueError(f"mode must be an instance of RoutingMode, got {self.mode!r}")

    def canonical_bytes(self) -> bytes:
        """Canonical, domain-separated UTF-8 JSON key serialization."""
        payload = {
            "version": ALGORITHM_VERSION,
            "domain": DOMAIN_SEPARATOR,
            "mode": self.mode.value,
            "mission_id": self.mission_id,
            "role": self.role,
            "ordinal": self.ordinal,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class SelectionEvidence:
    """Deterministic selection audit trail and evidence."""
    selected_endpoint: str
    bucket: int
    total_weight_units: int
    effective_candidates: tuple[str, ...]
    excluded_candidates: tuple[str, ...]
    selection_key_digest: str
    algorithm_version: int = ALGORITHM_VERSION


def _to_exact_integer_units(candidates: Sequence[CandidateWeight]) -> tuple[tuple[str, int], ...]:
    """Convert candidate weights to exact integer units via decimal normalization."""
    decimals: list[tuple[str, Decimal]] = []
    max_scale = 0
    for c in candidates:
        d = Decimal(str(c.weight))
        decimals.append((c.endpoint_id, d))
        scale = -d.as_tuple().exponent if d.as_tuple().exponent < 0 else 0
        if scale > max_scale:
            max_scale = scale

    multiplier = Decimal(10**max_scale)
    units: list[tuple[str, int]] = []
    for ep, d in decimals:
        unit_val = int(d * multiplier)
        if unit_val <= 0 and d > Decimal(0):
            unit_val = 1
        units.append((ep, unit_val))
    return tuple(units)


def weighted_select(
    candidates: Sequence[CandidateWeight],
    key: SelectionKey,
    exclude: Collection[str] | None = None,
) -> SelectionEvidence:
    """Select a candidate deterministically using stable SHA-256 integer-exact cumulative walk.

    Algorithm (Task 3R integer-exact):
    - Converts weights to exact integer units.
    - Hashes canonical key via SHA-256.
    - Computes exact integer bucket: bucket = (raw_int * total_units) >> 64
      where 0 <= bucket < total_units.
    - Walks sorted integer cumulative bounds without floating-point arithmetic.
    """
    if not isinstance(key, SelectionKey):
        raise TypeError(f"key must be a SelectionKey, got {type(key).__name__}")

    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        raise TypeError(f"candidates must be a sequence of CandidateWeight, got {type(candidates).__name__}")

    excluded_set = set(exclude or ())
    seen_endpoints = set()
    survivors: list[CandidateWeight] = []
    excluded_found: list[str] = []

    for c in candidates:
        if not isinstance(c, CandidateWeight):
            raise TypeError(f"candidate element must be CandidateWeight, got {type(c).__name__}")
        ep = c.endpoint_id
        if ep in seen_endpoints:
            raise ValueError(f"duplicate candidate endpoint in input table: {ep!r}")
        seen_endpoints.add(ep)

        # Defensive weight checks
        w = c.weight
        if isinstance(w, bool) or not isinstance(w, (int, float)):
            raise ValueError(f"invalid weight type {type(w).__name__} for endpoint {ep!r}")
        if math.isnan(w) or math.isinf(w) or w < 0:
            raise ValueError(f"invalid weight value {w!r} for endpoint {ep!r}")

        if ep in excluded_set:
            excluded_found.append(ep)
        else:
            survivors.append(c)

    if not survivors:
        raise NoEligibleCandidateError("No eligible candidate remaining after exclusions.")

    # Canonical order by exact endpoint_id for deterministic bucket walk
    canonical_survivors = sorted(survivors, key=lambda c: c.endpoint_id)
    units_table = _to_exact_integer_units(canonical_survivors)
    total_units = sum(u for _, u in units_table)

    key_bytes = key.canonical_bytes()
    digest_bytes = hashlib.sha256(key_bytes).digest()
    digest_hex = hashlib.sha256(key_bytes).hexdigest()

    # Exact integer bucket mapping in [0, total_units) using 64-bit multiply-and-shift
    raw_int = int.from_bytes(digest_bytes[:8], "big")
    bucket = (raw_int * total_units) >> 64

    cumulative = 0
    selected = canonical_survivors[-1].endpoint_id

    for ep, unit_w in units_table:
        cumulative += unit_w
        if bucket < cumulative:
            selected = ep
            break

    return SelectionEvidence(
        selected_endpoint=selected,
        bucket=bucket,
        total_weight_units=total_units,
        effective_candidates=tuple(c.endpoint_id for c in canonical_survivors),
        excluded_candidates=tuple(sorted(excluded_found)),
        selection_key_digest=digest_hex,
        algorithm_version=ALGORITHM_VERSION,
    )


def select_candidate(
    policy: RuntimePolicy,
    candidates: Sequence[CandidateWeight],
    key: SelectionKey,
    additional_exclusions: Collection[str] | None = None,
) -> SelectionEvidence:
    """Convenience helper: filter unverified policy endpoints then select."""
    exclusions = set(additional_exclusions or ())

    # Filter any endpoint marked unverified or ineligible in policy metadata
    for ep, meta in policy.endpoint_resolution.items():
        if not meta.get("verified", False) or meta.get("eligibility") != "eligible":
            exclusions.add(ep)

    return weighted_select(candidates, key, exclude=exclusions)
