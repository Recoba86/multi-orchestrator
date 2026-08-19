# Multi Orchestrator Architecture (RC3 — Dedicated Boss)

## Overview

Multi Orchestrator implements a 3-plane Hub-and-Spoke architecture:

1. **Control Plane (Root Controller):** The model selected in the active session/UI. Responsible for validating all Boss actions against Core policy, executing exact subagent spawns, relaying factual results without mutation, managing Mission Trace persistence, and enforcing fail-closed invariants.
2. **Decision Plane (Dedicated Skill-Bound Boss):** A dedicated child subagent spawned on the exact model required by the invoked skill (Sol High for `sol-luna-orchestrator-v2`, Grok High for `grok-orchestrator-v2`). Responsible for task planning, packet formation, role selection, verifier assignment, and final acceptance.
3. **Execution Plane (Workers / Scouts / Verifiers / Reviewers):** Leaf execution subagents.

```text
      User / Developer
             │
             ▼
       ROOT_CONTROLLER
 (Session Model / Control Plane)
             │
             ▼ (spawns & relays)
      DEDICATED_BOSS
  (Skill-Bound: Sol High / Grok High)
             │ (decisions / actions)
             ▼
       ROOT_CONTROLLER
             │ (validated execution)
   ┌─────────┼─────────┬──────────────────────┬───────────────────────┐
   ▼         ▼         ▼                      ▼                       ▼
 Scout    Standard    Deep     Implementer-Aware   Premium        Dedicated Boss
(Read)     Worker    Worker         Verifier       Reviewer        (Decision Plane)
(gemini)   (gemini)    (dseek)     (!implementer)    (Opus)         (Sol / Grok)
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

## Six Hard Invariants

1. **Dedicated Boss Mandatory:** If the Skill-bound Boss cannot be bound on the required model/effort, the mission MUST fail closed with `BOSS_BINDING_UNAVAILABLE`.
2. **Root Controller Cannot Self-Promote:** The Root Controller MUST NOT take over as Boss or make autonomous orchestration decisions.
3. **One Persistent Boss Per Mission:** The same dedicated Boss child instance MUST be maintained across the entire mission via child follow-up tasks (`followup_task`).
4. **Structured/Lossless Factual Relay:** All inter-plane communication occurs via explicit structured packets (`BOSS_MISSION_PACKET`, `BOSS_ACTION_PACKET`, `CHILD_EXECUTION_RESULT`, `BOSS_FOLLOWUP_PACKET`, `FINAL_BOSS_DECISION`).
5. **Controller Validates Every Action:** The Root Controller strictly validates every Boss request against Core policy before execution.
6. **Runtime Observability:** Live runtime binding evidence is recorded in `~/.codex/orchestrator-traces/<mission_id>.json`.
