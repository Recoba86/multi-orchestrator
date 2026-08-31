# Multi Orchestrator Architecture (RC3 — Dedicated Boss)

## Overview

Multi Orchestrator implements a 3-plane Hub-and-Spoke architecture:

1. **Control Plane (Root Controller):** The model selected in the active session/UI. Responsible for validating Boss actions against Core policy, submitting protocol-validated requests to the external Codex Host, relaying Host-returned facts, managing Mission Trace persistence, and refusing invalid submissions or continuation.
2. **Decision Plane (Dedicated Skill-Bound Boss):** A dedicated child requested at the endpoint/model required by the invoked skill (`gpt-5.6-sol` High for `$autoteam`) and accepted only after matching runtime evidence. Responsible for task planning, packet formation, role selection, verifier assignment, and final acceptance.
3. **Execution Plane (Workers / Scouts / Verifiers / Reviewers):** Leaf execution subagents.

```text
      User / Developer
             │
             ▼
       ROOT_CONTROLLER
 (Session Model / Control Plane)
             │
             ▼ (submits Host requests & relays)
      DEDICATED_BOSS
  (Skill-Bound: canonical BOSS chain)
             │ (decisions / actions)
             ▼
       ROOT_CONTROLLER
             │ (protocol-validated Host requests)
   ┌─────────┼─────────┬──────────────────────┬───────────────────────┐
   ▼         ▼         ▼                      ▼                       ▼
 Scout    Standard    Deep     Implementer-Aware   Premium        Dedicated Boss
(Read)     Worker    Worker         Verifier       Reviewer        (Decision Plane)
(Gemini)   (Gemini)    (Grok)      (!implementer)    (Opus)       (same canonical chain)
   │         │         │              │               │               ▲
   └─────────┼─────────┴──────────────┴───────────────┴───────────────┘
             │ (Structured Factual Execution Results)
             ▼
       ROOT_CONTROLLER
             │ (lossless relay via follow-up)
             │
             └────────────────────────────────────────────────────────┘
             │
             ▼
      User / Developer
```

## Declarative model configuration (non-executable)

The repository also ships [`config/models.yaml`](../config/models.yaml), a
provider-agnostic, user-editable operator policy. Its `operator_policy` section
defines the exact ordered model/effort chains for BOSS/Planner, Scout, Standard
Worker, Deep Worker, Verifier, and Premium Second Opinion. The four logical
roles (`planner`, `scout`, `worker`, and `reviewer`) remain advisory views for
Doctor and the offline resolver.

This file serves as advisory configuration. Centralized policy semantics in
`core/model_policy.py` and deterministic offline advisory resolution in
`core/model_resolver.py` (`resolve_role`) evaluate discovered declarations,
offline availability observations, capability compatibility, and intelligence
profiles. Doctor renders structured resolution outcomes, while `configure-models`
provides explicit, approved configuration updates. These tools are strictly
offline and advisory; they never mutate Host state or probe remote providers.
Runtime endpoint IDs are derived deterministically in
`config/runtime-routing.yaml`, whose validation rejects drift between the
operator policy and its compatibility views. SolMode and GrokMode remain
explicit state for compatibility and telemetry; they do not select alternate
model chains.

## Six Hard Invariants

1. **Dedicated Boss Mandatory:** If a matching Boss request cannot be submitted or Host-returned evidence does not establish the required child, the Controller MUST refuse protocol continuation with `BOSS_BINDING_UNAVAILABLE`.
2. **Root Controller Cannot Self-Promote:** The Root Controller MUST NOT take over as Boss or make autonomous orchestration decisions.
3. **One Persistent Boss Per Mission:** The same dedicated Boss child instance MUST be maintained across the entire mission via child follow-up tasks (`followup_task`).
4. **Structured/Lossless Factual Relay:** All inter-plane communication occurs via explicit structured packets (`BOSS_MISSION_PACKET`, `BOSS_ACTION_PACKET`, `CHILD_EXECUTION_RESULT`, `BOSS_FOLLOWUP_PACKET`, `FINAL_BOSS_DECISION`).
5. **Controller Validates Every Action:** The Root Controller validates every Boss request against Core policy before Host request submission.
6. **Runtime Observability:** Live runtime binding evidence is recorded in `~/.codex/orchestrator-traces/<mission_id>.json`.

## Execution Boundary

The repository controls protocol validation and request submission; native child allocation and resolved effective identity are `HOST_EXTERNAL`. It does not prove Host interception, pre-allocation authorization, or all-entry-point non-bypassability. `PreToolUse Agent` is only an optional guardrail. The authoritative guarantees, non-guarantees, and strict-integration requirements are in [Core's Execution Boundary Model](../core/ORCHESTRATOR_CORE.md#execution-boundary-model-host_external--authoritative).
