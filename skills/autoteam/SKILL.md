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

Native allocation and resolved effective identity remain `HOST_EXTERNAL`. The
wrapper controls protocol validation and request submission, and MUST pass the
validated model binding explicitly at the native Host boundary.

### Native Host task-name contract (mandatory)

Codex validates the native `task_name` as an `agent_name`. For every Auto Team
child, use a bare identifier matching `^[a-z0-9_]+$`:

- Generate a unique mission-scoped name such as
  `autoteam_scout_01_mission_1787106000`.
- Lowercase the role and mission slug, replace every character outside
  `[a-z0-9_]` with `_`, collapse repeated underscores, and validate the final
  value before calling `spawn_agent`.
- Never use a workspace path (for example `/root/...`), hyphens, spaces, or
  uppercase characters in `task_name`.
- If the final name is invalid, do not call the Host; report
  `HOST_AGENT_NAME_INVALID` and generate a corrected bare name.

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
2. **Request Dedicated Boss:** Controller checks master routing state. If master routing is enabled (`orchestrator-routing status` / `is_routing_enabled`), resolve the Boss from the canonical Auto Team policy (`route-model select --role BOSS`); the persisted SolMode/GrokMode value remains observable operator state and does not replace that policy. If disabled, submit default `SOL_HIGH` (`gpt-5.6-sol`, High effort). In either state, generate fresh `mission_id`, build `MISSION_IDENTITY`, and call native `spawn_agent` with top-level `model=<requested_model>`, `reasoning_effort=<requested_effort>`, `fork_turns="none"`, and the `BOSS_MISSION_PACKET`; continue only with a distinct Host-returned child identity whose effective binding is proven.
3. **Receive `BOSS_ACTION_PACKET`:** Validate `mission_id`, `workspace_root`, and `repository_identity` match `MISSION_IDENTITY`, then validate requested endpoint/model/effort against Core policy. On mismatch, refuse Host request submission with `MISSION_CONTEXT_MISMATCH`. On success, call native `spawn_agent` with the packet's validated top-level `model`, `reasoning_effort`, and `fork_turns="none"`; do not rely on the root/session model, parent inheritance, endpoint labels, or prompt text.
4. **Lossless Relay:** Controller captures `CHILD_EXECUTION_RESULT`, records trace entry, validates `boss_child_id` matches current mission Boss, and delivers `BOSS_FOLLOWUP_PACKET` to the SAME dedicated Boss.
5. **Final Decision & Identity Validation:** Boss issues `FINAL_BOSS_DECISION` carrying `mission_id`, `workspace_root`, `repository_identity`, and `boss_child_id`. Controller validates that all identity fields match `MISSION_IDENTITY`. If any field mismatches, abort with `FINAL_DECISION_CONTEXT_MISMATCH`. On successful validation, Controller finalizes Mission Trace, outputs Routing Decisions and Model Telemetry, and delivers factual summary to user.

### Native Host model binding (mandatory)

For every Auto Team child creation (`DEDICATED_BOSS`, `SCOUT`,
`STANDARD_WORKER`, `DEEP_WORKER`, `VERIFIER`, or
`PREMIUM_SECOND_OPINION`), the Controller MUST perform this sequence:

1. Select and validate the route candidate, including any policy-authorized
   failover or reviewer-independence filtering, before creating the child.
2. Inspect the effective native `spawn_agent` schema. The request MUST include
   the selected values as top-level Host arguments:

   ```text
   spawn_agent({
     task_name: <validated lowercase agent name>,
     fork_turns: "none",
     model: <validated requested_model>,
     reasoning_effort: <validated requested_effort>,
     message: <self-contained packet>
   })
   ```

   `model` and `reasoning_effort` are mandatory for Auto Team even though the
   native tool marks model overrides as optional for ordinary delegation.
   Packet text, `agent_type`, endpoint labels, and prompt instructions are not
   model binding substitutes.
3. If either override field is absent from the effective schema, rejected by
   the Host, or cannot be submitted with the selected route, stop before
   spawning and report `HOST_MODEL_BINDING_ERROR`. Do not retry with the
   parent/default model, silently omit the field, or launch a subprocess-based
   `codex -m ...` replacement.
4. After creation, obtain Host-returned child/session evidence for the effective
   model and reasoning effort. Record `requested_model`,
   `requested_effort`, `effective_model`, `effective_effort`, and
   `MATCH`/`MISMATCH`. Authoritative effective identity is defined by
   Host/session state (`threads.model`/`threads.reasoning_effort` in `~/.codex/state_5.sqlite`,
   or `turn_context.model` in child rollout). Note that `session_meta.base_instructions.provenance`
   merely records the root/parent session launcher, NOT the child agent's effective model.
   If either effective value is unavailable, record `UNPROVEN` and fail closed.
   If authoritative values differ, interrupt the child, record `HOST_MODEL_BINDING_ERROR`
   with `MISMATCH`, and do not relay a follow-up, select a post-spawn fallback, or continue.

`followup_task` preserves the already-bound child and is not a substitute for
explicit binding when creating a new child.

## Runtime Routing Activation

When master routing is **ENABLED** (`orchestrator-routing on` / `use SolMode` / `use GrokMode`):
1. **Canonical Role Policy:** SolMode and GrokMode use the same operator-selected Auto Team chains. Mode is retained for explicit operator state, status, telemetry, and compatibility; it is not a model-selection override.
2. **Worker Routing:** Subagents for `SCOUT`, `STANDARD_WORKER`, and `DEEP_WORKER` are resolved dynamically via the declarative runtime policy (`config/runtime-routing.yaml`).
3. **Reviewer Independence:** `VERIFIER` assignments enforce bidirectional independence (`Reviewer.model_family != Implementer.model_family`).
4. **Boss Continuity:** Dedicated Boss continuity across turns is strictly preserved.

When master routing is **DISABLED** (`orchestrator-routing off`):
- Exact legacy submitted-request authority is restored and default role chains apply.
