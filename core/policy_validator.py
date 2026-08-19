"""
Production Dynamic Policy Validator for Multi Orchestrator RC3.
Derives routing, canonical model strings, effort limits, endpoint registrations,
and verifier policies directly from the authoritative Shared Core (ORCHESTRATOR_CORE.md).
"""
import os
import re
import yaml
from typing import Dict, Any, Tuple, Optional

def load_policy_from_core(core_path: str) -> Dict[str, Any]:
    if not os.path.exists(core_path):
        raise FileNotFoundError(f"Authoritative core file not found: {core_path}")
    
    with open(core_path, "r", encoding="utf-8") as f:
        text = f.read()
    
    yaml_blocks = re.findall(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
    parsed_data = {}
    for block in yaml_blocks:
        try:
            loaded = yaml.safe_load(block)
            if isinstance(loaded, dict):
                parsed_data.update(loaded)
        except Exception:
            pass
    return parsed_data

class PolicyValidator:
    def __init__(self, core_path: Optional[str] = None):
        if core_path is None:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            core_path = os.path.join(repo_root, "core", "ORCHESTRATOR_CORE.md")
        self.core_path = core_path
        self.policy = load_policy_from_core(self.core_path)
        self.endpoints = {ep["id"]: ep for ep in self.policy.get("endpoints", [])}
        self.skill_boss_bindings = self.policy.get("skill_boss_bindings", {})
        self.role_chains = self.policy.get("role_chains", {})
        self.verifier_chains = self.policy.get("verifier_chains", {})

    def validate_boss_binding(self, skill_name: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if skill_name not in self.skill_boss_bindings:
            return False, "BOSS_BINDING_UNAVAILABLE: Unregistered skill", None
        binding = self.skill_boss_bindings[skill_name]
        
        ep_id = binding.get("required_boss_endpoint")
        if not ep_id:
            return False, f"BOSS_BINDING_UNAVAILABLE: Missing required_boss_endpoint in skill binding for {skill_name}", None
        if ep_id not in self.endpoints:
            return False, f"BOSS_BINDING_UNAVAILABLE: Endpoint {ep_id} not in registry", None
        
        req_model = binding.get("model")
        if not req_model:
            return False, f"BOSS_BINDING_UNAVAILABLE: Missing required model in skill binding for {skill_name}", None
        
        ep = self.endpoints[ep_id]
        expected_model = ep.get("model")
        if expected_model and req_model != expected_model:
            return False, f"BOSS_BINDING_UNAVAILABLE: Model mismatch for {ep_id} ({req_model} != {expected_model})", None
        
        req_effort = binding.get("effort")
        if not req_effort:
            return False, f"BOSS_BINDING_UNAVAILABLE: Missing required effort in skill binding for {skill_name}", None
        
        if req_effort not in ep.get("accepted_efforts", []):
            return False, f"BOSS_BINDING_UNAVAILABLE: Effort {req_effort} not in accepted_efforts {ep.get('accepted_efforts')}", None
        
        policy_max = ep.get("policy_max_effort")
        if policy_max:
            eff_levels = {"low": 1, "medium": 2, "high": 3, "max": 4}
            if eff_levels.get(req_effort, 0) > eff_levels.get(policy_max, 0):
                return False, f"BOSS_BINDING_UNAVAILABLE: Effort {req_effort} exceeds policy cap {policy_max}", None

        return True, None, binding

    def validate_role_not_controller_self_promotion(self, agent_type: str, requested_role: str) -> Tuple[bool, Optional[str]]:
        if agent_type == "ROOT_CONTROLLER" and requested_role in ["BOSS", "DEDICATED_BOSS", "DECISION_PLANE"]:
            return False, "REJECT_CONTROLLER_SELF_PROMOTION"
        return True, None

    def validate_requested_endpoint(self, endpoint_id: str) -> Tuple[bool, Optional[str]]:
        if endpoint_id not in self.endpoints:
            return False, f"REJECT_UNKNOWN_ENDPOINT: {endpoint_id}"
        return True, None

    def validate_endpoint_effort(self, endpoint_id: str, effort: str) -> Tuple[bool, Optional[str]]:
        if endpoint_id not in self.endpoints:
            return False, f"REJECT_UNKNOWN_ENDPOINT: {endpoint_id}"
        ep = self.endpoints[endpoint_id]
        if effort not in ep.get("accepted_efforts", []):
            return False, f"REJECT_UNACCEPTED_EFFORT: {effort} not in {ep.get('accepted_efforts')}"
        
        policy_max = ep.get("policy_max_effort")
        if policy_max:
            eff_levels = {"low": 1, "medium": 2, "high": 3, "max": 4}
            if eff_levels.get(effort, 0) > eff_levels.get(policy_max, 0):
                return False, f"REJECT_EFFORT_EXCEEDS_POLICY: {effort} > {policy_max}"
        return True, None

    def validate_controller_execution_binding(
        self,
        requested_ep: str,
        requested_model: str,
        requested_effort: str,
        executed_ep: str,
        actual_model: str,
        executed_effort: str
    ) -> Tuple[bool, Optional[str]]:
        # 1. Requested endpoint exists
        if requested_ep not in self.endpoints:
            return False, f"REJECT_UNKNOWN_ENDPOINT: {requested_ep}"
        
        ep = self.endpoints[requested_ep]
        canonical_model = ep.get("model")

        # 2. Requested model == canonical model
        if canonical_model and requested_model != canonical_model:
            return False, f"REJECT_REQUESTED_MODEL_MISMATCH: Requested model '{requested_model}' does not match canonical '{canonical_model}' for {requested_ep}"

        # 3. Executed endpoint == requested endpoint
        if executed_ep != requested_ep:
            return False, f"REJECT_CONTROLLER_SUBSTITUTION: Endpoint mismatch ({requested_ep} != {executed_ep})"

        # 4. Actual executed model == canonical model for endpoint
        if canonical_model and actual_model != canonical_model:
            return False, f"REJECT_CONTROLLER_MODEL_SUBSTITUTION: Actual executed model '{actual_model}' does not match canonical '{canonical_model}' for {requested_ep}"

        # 5. Executed effort == requested effort
        if executed_effort != requested_effort:
            return False, f"REJECT_CONTROLLER_SUBSTITUTION: Effort mismatch ({requested_effort} != {executed_effort})"

        # 6. Requested effort is accepted by endpoint
        if requested_effort not in ep.get("accepted_efforts", []):
            return False, f"REJECT_UNACCEPTED_EFFORT: {requested_effort} not in {ep.get('accepted_efforts')}"

        # 7. Policy cap check
        policy_max = ep.get("policy_max_effort")
        if policy_max:
            eff_levels = {"low": 1, "medium": 2, "high": 3, "max": 4}
            if eff_levels.get(requested_effort, 0) > eff_levels.get(policy_max, 0):
                return False, f"REJECT_EFFORT_EXCEEDS_POLICY: {requested_effort} > {policy_max}"

        return True, None

    def validate_verifier_independence(self, implementer_id: str, verifier_id: str) -> Tuple[bool, Optional[str]]:
        if implementer_id not in self.endpoints:
            return False, f"REJECT_UNKNOWN_ENDPOINT: {implementer_id}"
        if verifier_id not in self.endpoints:
            return False, f"REJECT_UNKNOWN_ENDPOINT: {verifier_id}"
        
        # 1. Exact self-verification conflict
        if implementer_id == verifier_id:
            return False, "REJECT_SELF_VERIFICATION"
        
        # 2. Model family conflict (e.g. PLUS_LUNA <-> OCG_LUNA)
        imp_fam = self.endpoints[implementer_id].get("family")
        ver_fam = self.endpoints[verifier_id].get("family")
        if imp_fam and ver_fam and imp_fam == ver_fam:
            return False, f"REJECT_MODEL_FAMILY_CONFLICT: Both endpoints belong to family '{imp_fam}'"
        
        return True, None
