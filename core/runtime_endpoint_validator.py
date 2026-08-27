"""Runtime endpoint and catalog validation layer (Task 12 Phase D).

Validates requested endpoints against legacy Core registry OR explicitly configured
and verified runtime catalog endpoints in config/runtime-routing.yaml.
Enforces that if an endpoint exists in both Core and runtime catalog, their model
and effort metadata must agree exactly (no silent override/conflict).
"""

from __future__ import annotations

from typing import Optional, Tuple
from pathlib import Path

from core.policy_validator import PolicyValidator
from core.runtime_routing_policy import RuntimePolicy, load_runtime_policy

__all__ = [
    "RuntimeEndpointValidator",
]

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "runtime-routing.yaml"


class RuntimeEndpointValidator:
    """Validator that validates requested endpoints against Core OR runtime catalog."""

    def __init__(
        self,
        core_validator: Optional[PolicyValidator] = None,
        runtime_policy: Optional[RuntimePolicy] = None,
    ):
        self.core_validator = core_validator or PolicyValidator()
        self.runtime_policy = runtime_policy or load_runtime_policy(_DEFAULT_CONFIG_PATH)

    def validate_catalog_conflicts(self) -> Tuple[bool, Optional[str]]:
        """Verify that runtime catalog does not conflict with existing Core endpoints."""
        for ep_id, meta in self.runtime_policy.endpoint_resolution.items():
            if ep_id in self.core_validator.endpoints:
                core_ep = self.core_validator.endpoints[ep_id]
                core_model = core_ep.get("model")
                cat_model = meta.get("model")
                if core_model and cat_model and core_model != cat_model:
                    return False, f"REJECT_CORE_OVERRIDE_CONFLICT: Runtime catalog model '{cat_model}' conflicts with Core model '{core_model}' for {ep_id}"

                core_efforts = set(core_ep.get("accepted_efforts", []))
                cat_effort = meta.get("effort")
                if cat_effort and core_efforts and cat_effort not in core_efforts:
                    return False, f"REJECT_CORE_EFFORT_CONFLICT: Runtime catalog effort '{cat_effort}' not in Core accepted efforts {core_efforts} for {ep_id}"
        return True, None

    def validate_endpoint(self, endpoint_id: str, effort: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Validate if an endpoint is valid under Core registry OR valid active runtime catalog."""
        # 1. Check for conflict if endpoint exists in both Core and catalog
        if endpoint_id in self.core_validator.endpoints and endpoint_id in self.runtime_policy.endpoint_resolution:
            core_ep = self.core_validator.endpoints[endpoint_id]
            meta = self.runtime_policy.endpoint_resolution[endpoint_id]
            core_model = core_ep.get("model")
            cat_model = meta.get("model")
            if core_model and cat_model and core_model != cat_model:
                return False, f"REJECT_CORE_OVERRIDE_CONFLICT: Runtime catalog model '{cat_model}' conflicts with Core model '{core_model}' for {endpoint_id}"

        # 2. Check if it's directly valid in Core
        core_ok, core_err = self.core_validator.validate_requested_endpoint(endpoint_id)
        if core_ok:
            if effort:
                eff_ok, eff_err = self.core_validator.validate_endpoint_effort(endpoint_id, effort)
                if not eff_ok:
                    return False, f"INVALID_EFFORT: {eff_err}"
            return True, None

        # 3. If not in Core, check if it's in the active runtime catalog
        if endpoint_id not in self.runtime_policy.endpoint_resolution:
            return False, f"REJECT_UNKNOWN_ENDPOINT: {endpoint_id} not in Core or runtime catalog"

        meta = self.runtime_policy.endpoint_resolution[endpoint_id]
        if not meta.get("enabled", True):
            return False, f"REJECT_DISABLED_ENDPOINT: {endpoint_id} is disabled in runtime catalog"

        if not meta.get("verified", False) or meta.get("eligibility") != "eligible":
            return False, f"REJECT_UNVERIFIED_ENDPOINT: {endpoint_id} is not verified/eligible"

        if effort:
            expected_effort = meta.get("effort")
            if expected_effort and effort != expected_effort:
                return False, f"REJECT_EFFORT_MISMATCH: Requested effort '{effort}' does not match catalog '{expected_effort}' for {endpoint_id}"

        return True, None
