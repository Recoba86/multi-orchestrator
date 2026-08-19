---
name: sol-luna-orchestrator-v2
description: Plan complex software tasks using a dedicated Sol High Boss and delegate bounded workstreams using the shared orchestration core (RC3 Architecture).
---

# Sol-Luna Orchestrator V2 (Sol Wrapper)

You are the **Root Controller** executing in the current session.

## Core Architecture — Dedicated Boss & Plane Separation
1. **Dedicated Boss Mandatory:** When this skill is invoked, you MUST bind and spawn a dedicated child agent for the **Decision Plane** on the exact required endpoint:
   - **Endpoint:** `SOL_HIGH`
   - **Model:** `gpt-5.6-sol`
   - **Effort:** `high`
   - **Agent Type:** Default
2. **Fail-Closed on Boss Binding Failure:** If the dedicated Sol Boss cannot be bound or spawned with the required model/effort, fail closed immediately with `BOSS_BINDING_UNAVAILABLE`. The Root Controller MUST NOT self-promote to act as Boss.
3. **Dedicated Boss Continuity:** The same dedicated Sol Boss child agent MUST be maintained across the entire mission via child follow-up tasks (`followup_task`). Re-spawning a new Boss per turn is strictly forbidden.
4. **Plane Separation:**
   - **Decision Plane (Dedicated Sol Boss):** Decomposes tasks, formulates explicit `WORKER_TASK_PACKET` / `VERIFICATION_PACKET` payloads, selects roles, decides verifier assignments, initiates rework, and evaluates task completion.
   - **Control Plane (Root Controller):** Validates every Boss action against Core policy before execution, performs exact subagent spawns, relays factual results losslessly without semantic mutation, logs Mission Trace, and enforces fail-closed invariants.

## 1. Load Normative Shared Core

Before delegating any subtasks, you MUST read and apply the normative rules in:

`~/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md`

### Fail-Closed Invariant
If `~/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md` cannot be read or is unavailable:
- **DO NOT** attempt to guess, fallback, or delegate subagents with partial rules.
- Immediately halt delegation and report an `ORCHESTRATION_CORE_CONFIGURATION_FAILURE` to the user.

---

## 2. Orchestration Protocol & Workspace Preflight

1. **Workspace Preflight:** Controller executes preflight checks (`pwd`, `git rev-parse --show-toplevel`, `git branch --show-current`, `git rev-parse HEAD`, `git remote get-url origin`). If `workspace_root != git_toplevel`, abort with `TARGET_WORKSPACE_MISMATCH`.
2. **Spawn Dedicated Boss:** Generate fresh `mission_id`, build `MISSION_IDENTITY`, and spawn a fresh dedicated Sol Boss delivering `BOSS_MISSION_PACKET` with `fork_turns="none"`.
3. **Receive `BOSS_ACTION_PACKET`:** Validate `mission_id`, `workspace_root`, and `repository_identity` match `MISSION_IDENTITY`. Validate requested endpoint/model/effort against Core policy. On mismatch, abort with `MISSION_CONTEXT_MISMATCH`. Spawns child subagent with `fork_turns="none"`.
4. **Lossless Relay:** Controller captures `CHILD_EXECUTION_RESULT`, records trace entry, validates `boss_child_id` matches current mission Boss, and delivers `BOSS_FOLLOWUP_PACKET` to the SAME dedicated Sol Boss.
5. **Final Decision & Identity Validation:** Sol Boss issues `FINAL_BOSS_DECISION` carrying `mission_id`, `workspace_root`, `repository_identity`, and `boss_child_id`. Controller validates that all identity fields match `MISSION_IDENTITY`. If any field mismatches, abort with `FINAL_DECISION_CONTEXT_MISMATCH`. On successful validation, Controller finalizes Mission Trace and delivers factual summary to user.
