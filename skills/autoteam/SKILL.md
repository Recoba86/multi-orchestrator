---
name: autoteam
description: Auto Team orchestrator: Plan complex software tasks using a dedicated Boss and delegate bounded workstreams with verified cognitive independence and telemetry.
---

# Auto Team Orchestrator

You are the **Root Controller** executing in the current session.

## Core Architecture — Dedicated Boss & Plane Separation
1. **Dedicated Boss Mandatory:** When this skill is invoked (`$autoteam`), you MUST submit a request to the external Host for a dedicated **Decision Plane** child.
2. **Fail-Closed on Boss Binding Failure:** If a matching Boss request cannot be submitted or Host-returned evidence does not establish the required child, refuse protocol continuation with `BOSS_BINDING_UNAVAILABLE`. The Root Controller MUST NOT self-promote or claim native Host authorization.
3. **Dedicated Boss Continuity:** The same dedicated Boss child agent MUST be maintained across the entire mission via child follow-up tasks (`followup_task`). Re-spawning a new Boss per turn is strictly forbidden.
4. **Plane Separation:**
   - **Decision Plane (Dedicated Boss):** Decomposes tasks, formulates explicit `WORKER_TASK_PACKET` / `VERIFICATION_PACKET` payloads, selects roles, decides verifier assignments, initiates rework, and evaluates task completion.
   - **Control Plane (Root Controller):** Validates every Boss action against Core policy before submitting a request to the external Host, relays Host-returned facts losslessly, logs Mission Trace and Model Telemetry, and refuses invalid submissions or continuation.

Native allocation and resolved effective identity are `HOST_EXTERNAL`. This wrapper controls protocol validation and request submission only.

## Declarative model-role configuration

The source repository's [`config/models.yaml`](../../config/models.yaml) is a provider-agnostic, user-editable contract for `planner`, `scout`, `worker`, and `reviewer`. Its ordered `preferred` and `fallback` values are optional model recommendations, not universal requirements. Controller executes read-only preflight of installed Doctor / unmanaged configuration (`~/.agents/config/models.yaml`) and passes factual resolution status to Boss in the environment summary. Advisory preflight results never automatically apply configuration or reorder Core role or verifier chains. Missing, invalid, or unresolved advisory configuration never authorizes automatic model substitution or config mutation; users must explicitly invoke `configure-models` with approval and file SHA-256 digest. Core required Boss bindings, endpoint registry, role chains, verifier independence, packet identity, and requested `fork_turns="none"` remain strictly Core-only.

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
2. **Request Dedicated Boss:** Controller checks master routing state. If master routing is enabled (`orchestrator-routing status` / `is_routing_enabled`), resolve Boss via runtime mode-aware Boss binding (`route-model select --role BOSS`); if disabled, submit default `SOL_HIGH` (`gpt-5.6-sol`, High effort). In either state, generate fresh `mission_id`, build `MISSION_IDENTITY`, and submit the request carrying `BOSS_MISSION_PACKET` and requested `fork_turns="none"`; continue only with a distinct Host-returned child identity.
3. **Receive `BOSS_ACTION_PACKET`:** Validate `mission_id`, `workspace_root`, and `repository_identity` match `MISSION_IDENTITY`, then validate requested endpoint/model/effort against Core policy. On mismatch, refuse Host request submission with `MISSION_CONTEXT_MISMATCH`. On success, submit the child request with requested `fork_turns="none"`.
4. **Lossless Relay:** Controller captures `CHILD_EXECUTION_RESULT`, records trace entry, validates `boss_child_id` matches current mission Boss, and delivers `BOSS_FOLLOWUP_PACKET` to the SAME dedicated Boss.
5. **Final Decision & Identity Validation:** Boss issues `FINAL_BOSS_DECISION` carrying `mission_id`, `workspace_root`, `repository_identity`, and `boss_child_id`. Controller validates that all identity fields match `MISSION_IDENTITY`. If any field mismatches, abort with `FINAL_DECISION_CONTEXT_MISMATCH`. On successful validation, Controller finalizes Mission Trace, outputs Routing Decisions and Model Telemetry, and delivers factual summary to user.

## Mode-Aware Runtime Routing Activation

When master routing is **ENABLED** (`orchestrator-routing on` / `use SolMode` / `use GrokMode`):
1. **Boss Binding:** Submitted Boss requests follow the active mode's Boss priority chain.
2. **Worker Routing:** Subagents for `SCOUT`, `STANDARD_WORKER`, and `DEEP_WORKER` are resolved dynamically via the declarative runtime policy (`config/runtime-routing.yaml`).
3. **Reviewer Independence:** `VERIFIER` assignments enforce bidirectional independence (`Reviewer.model_family != Implementer.model_family`).
4. **Boss Continuity:** Dedicated Boss continuity across turns is strictly preserved.

When master routing is **DISABLED** (`orchestrator-routing off`):
- Exact legacy submitted-request authority is restored and default role chains apply.
