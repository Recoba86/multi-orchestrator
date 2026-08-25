#!/usr/bin/env python3
"""
Tests for Canonical Mission Identity & Workspace Isolation Invariants.
Validates:
- MISSION_IDENTITY schema completeness
- Preflight workspace match & mismatch fail-closed
- All 5 packet validators:
  1. BOSS_MISSION_PACKET
  2. BOSS_ACTION_PACKET (including FORK_TURNS_NONE_REQUIRED)
  3. CHILD_EXECUTION_RESULT
  4. BOSS_FOLLOWUP_PACKET
  5. FINAL_BOSS_DECISION (including boss_child_id and FINAL_DECISION_CONTEXT_MISMATCH)
- Trace identity completeness, fork_turns enforcement & inherited_parent_turns validation
"""

import unittest
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "core"))

from identity_validator import (
    validate_mission_identity,
    validate_boss_mission_packet,
    validate_boss_action_packet,
    validate_child_execution_result,
    validate_boss_followup_packet,
    validate_final_boss_decision,
    validate_trace_identity_completeness
)

class TestMissionIdentityAndIsolation(unittest.TestCase):
    def setUp(self):
        self.valid_identity = {
            "mission_id": "mission-test-100",
            "skill": "sol-luna-orchestrator-v2",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "git_toplevel": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "starting_branch": "develop",
            "starting_sha": "627c6c58150ac618da53fb2c24ab889a277e4005",
            "boss_child_id": "sol_boss_test_100"
        }

    def test_valid_mission_identity(self):
        ok, err = validate_mission_identity(self.valid_identity)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_target_workspace_mismatch_fails_closed(self):
        bad_identity = dict(self.valid_identity)
        bad_identity["git_toplevel"] = "/Users/example/Documents/OtherProject"
        ok, err = validate_mission_identity(bad_identity)
        self.assertFalse(ok)
        self.assertIn("TARGET_WORKSPACE_MISMATCH", err)

    def test_missing_mission_identity_field_fails_closed(self):
        bad_identity = dict(self.valid_identity)
        del bad_identity["boss_child_id"]
        ok, err = validate_mission_identity(bad_identity)
        self.assertFalse(ok)
        self.assertIn("boss_child_id", err)

    def test_boss_mission_packet_validation(self):
        mission_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "skill_invoked": "sol-luna-orchestrator-v2",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "git_toplevel": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "user_goal": "Inspect identity"
        }
        ok, err = validate_boss_mission_packet(mission_pkt, self.valid_identity)
        self.assertTrue(ok)
        self.assertIsNone(err)

        bad_pkt = dict(mission_pkt, mission_id="wrong-id")
        ok, err = validate_boss_mission_packet(bad_pkt, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("MISSION_CONTEXT_MISMATCH", err)

    def test_boss_action_valid(self):
        action_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "action_id": "act-1",
            "action": "SPAWN_CHILD",
            "logical_task_id": "scout-identity",
            "fork_turns": "none"
        }
        ok, err = validate_boss_action_packet(action_pkt, self.valid_identity)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_boss_action_fork_turns_missing_fails_closed(self):
        action_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "action_id": "act-1",
            "action": "SPAWN_CHILD",
            "logical_task_id": "scout-identity"
        }
        ok, err = validate_boss_action_packet(action_pkt, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("FORK_TURNS_POLICY_VIOLATION", err)

    def test_boss_action_fork_turns_all_fails_closed(self):
        action_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "action_id": "act-1",
            "action": "SPAWN_CHILD",
            "logical_task_id": "scout-identity",
            "fork_turns": "all"
        }
        ok, err = validate_boss_action_packet(action_pkt, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("FORK_TURNS_POLICY_VIOLATION", err)

    def test_boss_action_wrong_mission_id_fails_closed(self):
        action_pkt = {
            "packet_version": 1,
            "mission_id": "mission-foreign-999",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "action_id": "act-1",
            "action": "SPAWN_CHILD",
            "fork_turns": "none"
        }
        ok, err = validate_boss_action_packet(action_pkt, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("MISSION_CONTEXT_MISMATCH", err)

    def test_boss_action_wrong_workspace_fails_closed(self):
        action_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/Documents/OtherProject",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "action_id": "act-1",
            "action": "SPAWN_CHILD",
            "fork_turns": "none"
        }
        ok, err = validate_boss_action_packet(action_pkt, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("MISSION_CONTEXT_MISMATCH", err)

    def test_boss_action_wrong_repository_fails_closed(self):
        action_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/OtherOrg/other-repo.git",
            "action_id": "act-1",
            "action": "SPAWN_CHILD",
            "fork_turns": "none"
        }
        ok, err = validate_boss_action_packet(action_pkt, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("MISSION_CONTEXT_MISMATCH", err)

    def test_child_execution_result_validation(self):
        result_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "action_id": "act-1",
            "child_id": "scout_child_1"
        }
        ok, err = validate_child_execution_result(result_pkt, self.valid_identity)
        self.assertTrue(ok)
        self.assertIsNone(err)

        bad_res = dict(result_pkt, workspace_root="/different/workspace")
        ok, err = validate_child_execution_result(bad_res, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("MISSION_CONTEXT_MISMATCH", err)

    def test_boss_followup_foreign_boss_child_fails_closed(self):
        followup_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "boss_child_id": "foreign_boss_999",
            "child_result": {}
        }
        ok, err = validate_boss_followup_packet(followup_pkt, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("MISSION_CONTEXT_MISMATCH", err)
        self.assertIn("boss_child_id", err)

    def test_final_boss_decision_validation(self):
        decision_pkt = {
            "packet_version": 1,
            "mission_id": "mission-test-100",
            "workspace_root": "/Users/example/multi-orchestrator/dev",
            "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
            "boss_child_id": "sol_boss_test_100",
            "decision": "COMPLETE"
        }
        ok, err = validate_final_boss_decision(decision_pkt, self.valid_identity)
        self.assertTrue(ok)
        self.assertIsNone(err)

        bad_dec = dict(decision_pkt, mission_id="foreign-mission")
        ok, err = validate_final_boss_decision(bad_dec, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("FINAL_DECISION_CONTEXT_MISMATCH", err)

        bad_dec = dict(decision_pkt, workspace_root="/foreign/workspace")
        ok, err = validate_final_boss_decision(bad_dec, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("FINAL_DECISION_CONTEXT_MISMATCH", err)

        bad_dec = dict(decision_pkt, repository_identity="https://github.com/Other/repo.git")
        ok, err = validate_final_boss_decision(bad_dec, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("FINAL_DECISION_CONTEXT_MISMATCH", err)

        bad_dec = dict(decision_pkt, boss_child_id="foreign_boss_child")
        ok, err = validate_final_boss_decision(bad_dec, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("FINAL_DECISION_CONTEXT_MISMATCH", err)

        bad_dec = dict(decision_pkt, decision="INVALID_STATE")
        ok, err = validate_final_boss_decision(bad_dec, self.valid_identity)
        self.assertFalse(ok)
        self.assertIn("Invalid decision", err)

    def test_trace_identity_completeness_and_fork_turns(self):
        valid_trace = {
            "mission": {"mission_id": "mission-test-100", "status": "COMPLETE"},
            "workspace": {
                "requested_workspace_root": "/Users/example/multi-orchestrator/dev",
                "actual_git_toplevel": "/Users/example/multi-orchestrator/dev",
                "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
                "branch_at_start": "develop",
                "starting_sha": "627c6c58150ac618da53fb2c24ab889a277e4005",
                "identity_match": True
            },
            "boss": {
                "requested_fork_turns": "none",
                "child_id": "sol_boss_test_100"
            },
            "actions": [
                {
                    "action_id": "act-1",
                    "controller_executed": {
                        "child_id": "scout-1",
                        "fork_turns": "none"
                    },
                    "context_isolation": {
                        "packet_only": True,
                        "requested_fork_turns": "none",
                        "inherited_parent_turns": "UNPROVEN"
                    }
                }
            ]
        }
        ok, err = validate_trace_identity_completeness(valid_trace)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_trace_missing_fork_turns_fails(self):
        bad_trace = {
            "mission": {"mission_id": "mission-test-100", "status": "COMPLETE"},
            "workspace": {
                "requested_workspace_root": "/Users/example/multi-orchestrator/dev",
                "actual_git_toplevel": "/Users/example/multi-orchestrator/dev",
                "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
                "branch_at_start": "develop",
                "starting_sha": "627c6c58150ac618da53fb2c24ab889a277e4005",
                "identity_match": True
            },
            "boss": {
                "requested_fork_turns": "none"
            },
            "actions": [
                {
                    "action_id": "act-1",
                    "controller_executed": {
                        "child_id": "scout-1"
                    },
                    "context_isolation": {
                        "packet_only": True,
                        "requested_fork_turns": "none",
                        "inherited_parent_turns": "UNPROVEN"
                    }
                }
            ]
        }
        ok, err = validate_trace_identity_completeness(bad_trace)
        self.assertFalse(ok)
        self.assertIn("fork_turns", err)

    def test_trace_missing_inherited_parent_turns_fails(self):
        bad_trace = {
            "mission": {"mission_id": "mission-test-100", "status": "COMPLETE"},
            "workspace": {
                "requested_workspace_root": "/Users/example/multi-orchestrator/dev",
                "actual_git_toplevel": "/Users/example/multi-orchestrator/dev",
                "repository_identity": "https://github.com/Recoba86/multi-orchestrator.git",
                "branch_at_start": "develop",
                "starting_sha": "627c6c58150ac618da53fb2c24ab889a277e4005",
                "identity_match": True
            },
            "boss": {
                "requested_fork_turns": "none"
            },
            "actions": [
                {
                    "action_id": "act-1",
                    "controller_executed": {
                        "child_id": "scout-1",
                        "fork_turns": "none"
                    },
                    "context_isolation": {
                        "packet_only": True,
                        "requested_fork_turns": "none"
                        # inherited_parent_turns missing
                    }
                }
            ]
        }
        ok, err = validate_trace_identity_completeness(bad_trace)
        self.assertFalse(ok)
        self.assertIn("inherited_parent_turns", err)

if __name__ == "__main__":
    unittest.main()
