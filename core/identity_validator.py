"""
Canonical Mission Identity & Packet Validator for Multi Orchestrator RC3.
Provides pure, executable schema and identity validation functions.
"""
from typing import Dict, Any, Tuple, Optional

def validate_mission_identity(identity: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    required_fields = [
        "mission_id",
        "skill",
        "workspace_root",
        "git_toplevel",
        "repository_identity",
        "starting_branch",
        "starting_sha",
        "boss_child_id"
    ]
    for field in required_fields:
        if field not in identity or not identity[field]:
            return False, f"Missing or empty required field in MISSION_IDENTITY: {field}"
    
    if identity["workspace_root"] != identity["git_toplevel"]:
        return False, f"TARGET_WORKSPACE_MISMATCH: workspace_root ({identity['workspace_root']}) != git_toplevel ({identity['git_toplevel']})"
    
    return True, None

def validate_boss_mission_packet(packet: Dict[str, Any], mission_identity: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(packet, dict):
        return False, "BOSS_MISSION_PACKET must be a dictionary"
    
    required_fields = ["mission_id", "skill_invoked", "workspace_root", "git_toplevel", "repository_identity", "user_goal"]
    for field in required_fields:
        if field not in packet or not packet[field]:
            return False, f"Missing or empty required field in BOSS_MISSION_PACKET: {field}"
    
    if packet.get("mission_id") != mission_identity.get("mission_id"):
        return False, f"MISSION_CONTEXT_MISMATCH: mission packet mission_id ({packet.get('mission_id')}) != mission ({mission_identity.get('mission_id')})"
    
    if packet.get("workspace_root") != mission_identity.get("workspace_root"):
        return False, f"MISSION_CONTEXT_MISMATCH: mission packet workspace_root ({packet.get('workspace_root')}) != mission ({mission_identity.get('workspace_root')})"
    
    if packet.get("repository_identity") != mission_identity.get("repository_identity"):
        return False, f"MISSION_CONTEXT_MISMATCH: mission packet repository_identity ({packet.get('repository_identity')}) != mission ({mission_identity.get('repository_identity')})"
    
    return True, None

def validate_boss_action_packet(packet: Dict[str, Any], mission_identity: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(packet, dict):
        return False, "BOSS_ACTION_PACKET must be a dictionary"
    
    # Required identity fields
    if packet.get("mission_id") != mission_identity.get("mission_id"):
        return False, f"MISSION_CONTEXT_MISMATCH: packet mission_id ({packet.get('mission_id')}) != mission ({mission_identity.get('mission_id')})"
    
    if packet.get("workspace_root") != mission_identity.get("workspace_root"):
        return False, f"MISSION_CONTEXT_MISMATCH: packet workspace_root ({packet.get('workspace_root')}) != mission ({mission_identity.get('workspace_root')})"
    
    if packet.get("repository_identity") != mission_identity.get("repository_identity"):
        return False, f"MISSION_CONTEXT_MISMATCH: packet repository_identity ({packet.get('repository_identity')}) != mission ({mission_identity.get('repository_identity')})"
    
    action = packet.get("action")
    if action not in ["SPAWN_CHILD", "MISSION_COMPLETE", "MISSION_BLOCKED", "REWORK_REQUIRED"]:
        return False, f"Invalid action in BOSS_ACTION_PACKET: {action}"
    
    # FORK_TURNS_NONE_REQUIRED invariant
    if action == "SPAWN_CHILD":
        fork_turns = packet.get("fork_turns")
        if fork_turns is None:
            return False, "FORK_TURNS_POLICY_VIOLATION: fork_turns field is missing in BOSS_ACTION_PACKET"
        if fork_turns != "none":
            return False, f"FORK_TURNS_POLICY_VIOLATION: invalid fork_turns value '{fork_turns}', must be 'none'"
    
    return True, None

def validate_child_execution_result(result: Dict[str, Any], mission_identity: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(result, dict):
        return False, "CHILD_EXECUTION_RESULT must be a dictionary"
    
    if result.get("mission_id") != mission_identity.get("mission_id"):
        return False, f"MISSION_CONTEXT_MISMATCH: child result mission_id ({result.get('mission_id')}) != mission ({mission_identity.get('mission_id')})"
    
    if result.get("workspace_root") != mission_identity.get("workspace_root"):
        return False, f"MISSION_CONTEXT_MISMATCH: child result workspace_root ({result.get('workspace_root')}) != mission ({mission_identity.get('workspace_root')})"
    
    if result.get("repository_identity") != mission_identity.get("repository_identity"):
        return False, f"MISSION_CONTEXT_MISMATCH: child result repository_identity ({result.get('repository_identity')}) != mission ({mission_identity.get('repository_identity')})"
    
    if not result.get("action_id") or not result.get("child_id"):
        return False, "Missing action_id or child_id in CHILD_EXECUTION_RESULT"
    
    return True, None

def validate_boss_followup_packet(packet: Dict[str, Any], mission_identity: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(packet, dict):
        return False, "BOSS_FOLLOWUP_PACKET must be a dictionary"
    
    if packet.get("mission_id") != mission_identity.get("mission_id"):
        return False, f"MISSION_CONTEXT_MISMATCH: followup mission_id ({packet.get('mission_id')}) != mission ({mission_identity.get('mission_id')})"
    
    if packet.get("workspace_root") != mission_identity.get("workspace_root"):
        return False, f"MISSION_CONTEXT_MISMATCH: followup workspace_root ({packet.get('workspace_root')}) != mission ({mission_identity.get('workspace_root')})"
    
    if packet.get("repository_identity") != mission_identity.get("repository_identity"):
        return False, f"MISSION_CONTEXT_MISMATCH: followup repository_identity ({packet.get('repository_identity')}) != mission ({mission_identity.get('repository_identity')})"
    
    if packet.get("boss_child_id") != mission_identity.get("boss_child_id"):
        return False, f"MISSION_CONTEXT_MISMATCH: followup boss_child_id ({packet.get('boss_child_id')}) != mission boss ({mission_identity.get('boss_child_id')})"
    
    return True, None

def validate_final_boss_decision(decision: Dict[str, Any], mission_identity: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    if not isinstance(decision, dict):
        return False, "FINAL_BOSS_DECISION must be a dictionary"
    
    if decision.get("mission_id") != mission_identity.get("mission_id"):
        return False, f"MISSION_CONTEXT_MISMATCH: final decision mission_id ({decision.get('mission_id')}) != mission ({mission_identity.get('mission_id')})"
    
    if decision.get("workspace_root") != mission_identity.get("workspace_root"):
        return False, f"MISSION_CONTEXT_MISMATCH: final decision workspace_root ({decision.get('workspace_root')}) != mission ({mission_identity.get('workspace_root')})"
    
    if decision.get("repository_identity") != mission_identity.get("repository_identity"):
        return False, f"MISSION_CONTEXT_MISMATCH: final decision repository_identity ({decision.get('repository_identity')}) != mission ({mission_identity.get('repository_identity')})"
    
    dec_val = decision.get("decision")
    if dec_val not in ["COMPLETE", "INCOMPLETE", "BLOCKED", "REWORK_REQUIRED"]:
        return False, f"Invalid decision value in FINAL_BOSS_DECISION: {dec_val}"
    
    return True, None

def validate_trace_identity_completeness(trace_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    workspace = trace_data.get("workspace", {})
    if not workspace:
        return False, "Missing workspace section in mission trace"
    
    req_ws_fields = ["requested_workspace_root", "actual_git_toplevel", "repository_identity", "branch_at_start", "starting_sha", "identity_match"]
    for field in req_ws_fields:
        if field not in workspace:
            return False, f"Missing field in trace workspace section: {field}"
    
    if not workspace.get("identity_match"):
        return False, "Trace records workspace identity mismatch"
    
    return True, None
