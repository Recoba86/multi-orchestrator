"""Read-only, provider-agnostic model capability metadata.

The catalog is intentionally descriptive.  It is not a resolver, a policy
engine, or evidence that a model can be reached or used in the current
runtime.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType


CAPABILITY_LABELS = (
    "reasoning",
    "coding",
    "fast",
    "long_context",
    "analysis",
    "review",
    "cost_effective",
)

STATUS_KNOWN = "KNOWN"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_COMPATIBLE = "COMPATIBLE"
STATUS_INCOMPATIBLE = "INCOMPATIBLE"

# Short status names keep call sites readable while retaining one source of
# truth for the exact public strings.
KNOWN = STATUS_KNOWN
UNKNOWN = STATUS_UNKNOWN
COMPATIBLE = STATUS_COMPATIBLE
INCOMPATIBLE = STATUS_INCOMPATIBLE

PROVENANCE_BUILTIN = "builtin-profile"
PROVENANCE_UNAVAILABLE = "metadata-unavailable"
METADATA_UNAVAILABLE = PROVENANCE_UNAVAILABLE


@dataclass(frozen=True)
class CapabilityMetadata:
    """One exact model identifier and its descriptive metadata."""

    model: str
    capabilities: tuple[str, ...]
    status: str
    provenance: str
    detail: str = ""

    @property
    def model_id(self) -> str:
        return self.model

    @property
    def labels(self) -> tuple[str, ...]:
        return self.capabilities

    @property
    def source(self) -> str:
        return self.provenance

    @property
    def known(self) -> bool:
        return self.status == STATUS_KNOWN


@dataclass(frozen=True)
class CompatibilityResult:
    """Advisory comparison of metadata with exact role capability hints."""

    model: str
    required: tuple[str, ...]
    capabilities: tuple[str, ...]
    status: str
    provenance: str
    missing: tuple[str, ...] = ()
    detail: str = ""

    @property
    def compatible(self) -> bool | None:
        if self.status == STATUS_COMPATIBLE:
            return True
        if self.status == STATUS_INCOMPATIBLE:
            return False
        return None

    @property
    def result(self) -> str:
        return self.status


def _profile(*capabilities: str) -> tuple[str, ...]:
    return tuple(capabilities)


# These are stable, descriptive defaults only.  Keep identifiers exact: no
# aliases, provider normalization, or fuzzy matching belongs in this module.
BUILTIN_CAPABILITY_PROFILES = MappingProxyType(
    {
        "gpt-5.6-sol": _profile(
            "reasoning", "coding", "long_context", "analysis", "review"
        ),
        "nine-router/gcli/grok-4.6-high": _profile(
            "reasoning", "long_context", "analysis"
        ),
        "gpt-5.6-luna": _profile(
            "reasoning", "coding", "fast", "analysis", "cost_effective"
        ),
        "opencode-go/deepseek-v4-pro": _profile(
            "reasoning", "coding", "long_context", "analysis"
        ),
        "nine-router/ag/gemini-3.7-flash-high": _profile(
            "reasoning", "coding", "fast", "analysis", "cost_effective"
        ),
        "opencode-go/deepseek-v4-flash": _profile(
            "coding", "fast", "analysis", "cost_effective"
        ),
        "opencode-go-responses/gpt-5.6-luna": _profile(
            "reasoning", "coding", "fast", "analysis", "cost_effective"
        ),
        "nine-router/ag/claude-opus-4-6-thinking": _profile(
            "reasoning", "long_context", "analysis", "review"
        ),
    }
)

# A descriptive alias makes the catalog's intent explicit without creating a
# second mutable source of truth.
BUILTIN_MODEL_CAPABILITIES = BUILTIN_CAPABILITY_PROFILES
BUILTIN_PROFILES = BUILTIN_CAPABILITY_PROFILES


def lookup_model_capabilities(model: str) -> CapabilityMetadata:
    """Return exact built-in metadata, or UNKNOWN when none is available."""
    if type(model) is not str:
        return CapabilityMetadata(
            "",
            (),
            STATUS_UNKNOWN,
            PROVENANCE_UNAVAILABLE,
            PROVENANCE_UNAVAILABLE,
        )

    capabilities = BUILTIN_CAPABILITY_PROFILES.get(model)
    if capabilities is None:
        return CapabilityMetadata(
            model,
            (),
            STATUS_UNKNOWN,
            PROVENANCE_UNAVAILABLE,
            PROVENANCE_UNAVAILABLE,
        )

    return CapabilityMetadata(
        model,
        tuple(capabilities),
        STATUS_KNOWN,
        PROVENANCE_BUILTIN,
        PROVENANCE_BUILTIN,
    )


def capability_hints_for_role(
    configuration: Mapping[str, Mapping[str, object]], role: str
) -> tuple[str, ...]:
    """Read user-owned hints without normalizing or interpreting their values."""
    if not isinstance(configuration, Mapping):
        return ()
    entry = configuration.get(role)
    if not isinstance(entry, Mapping):
        return ()
    hints = entry.get("capability_hints")
    if isinstance(hints, str):
        return (hints,)
    if not isinstance(hints, Iterable):
        return ()
    return tuple(item for item in hints if type(item) is str)


def assess_role_compatibility(
    model: str, required_capabilities: Iterable[str] | str
) -> CompatibilityResult:
    """Compare exact hints with metadata as advisory compatibility only."""
    if isinstance(required_capabilities, str):
        required = (required_capabilities,)
    else:
        required = tuple(
            item for item in required_capabilities if type(item) is str
        )

    metadata = lookup_model_capabilities(model)
    if metadata.status != STATUS_KNOWN:
        return CompatibilityResult(
            metadata.model,
            required,
            metadata.capabilities,
            STATUS_UNKNOWN,
            metadata.provenance,
            detail=PROVENANCE_UNAVAILABLE,
        )

    unknown_hints = tuple(
        capability
        for capability in required
        if capability not in CAPABILITY_LABELS
    )
    if unknown_hints:
        return CompatibilityResult(
            metadata.model,
            required,
            metadata.capabilities,
            STATUS_UNKNOWN,
            metadata.provenance,
            detail="unknown capability hint",
        )

    missing = tuple(
        capability
        for capability in required
        if capability not in metadata.capabilities
    )
    status = STATUS_INCOMPATIBLE if missing else STATUS_COMPATIBLE
    return CompatibilityResult(
        metadata.model,
        required,
        metadata.capabilities,
        status,
        metadata.provenance,
        missing,
    )


# Keep the public vocabulary small while allowing callers to use the natural
# noun form when reading the API.
role_compatibility = assess_role_compatibility
model_capabilities = lookup_model_capabilities
get_model_capabilities = lookup_model_capabilities
get_role_compatibility = assess_role_compatibility
