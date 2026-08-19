# Shared Orchestrator Core (Normative RC3 Architecture — Skill-Bound Dedicated Boss)

This document defines the normative, engine-agnostic orchestration policy, skill-to-boss bindings, endpoint registry, role routing, packet contracts, failure-handling rules, mission-scoped health circuit breakers, implementer-aware independent verification, strict reviewer isolation, and runtime mission tracing for Release Candidate 3 (RC3).

---

## 1. System Topology & Delegation Invariants

### A. Strict Hub-and-Spoke Invariant (`TOPOLOGY_HUB_AND_SPOKE_ONLY`)
The system strictly operates as a centralized Hub-and-Spoke topology:
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
(gemini)   (luna)    (dseek)     (!implementer)    (Opus)         (Sol / Grok)
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

### B. Plane Separation & Invariants
1. **DECISION PLANE (Dedicated Skill-Bound Boss):** The dedicated child agent bound to the exact model required by the invoked Skill (e.g. Grok for `grok-orchestrator-v2`, Sol for `sol-luna-orchestrator-v2`). Responsible for task understanding, decomposition, role selection, verifier assignment, rework decisions, and task completion evaluation.
2. **CONTROL PLANE (Root Controller):** The model selected in the active session/UI. Responsible strictly for validating Boss actions against Core policy, executing exact agent spawns, relaying factual results without semantic mutation, managing mission trace persistence, and failing closed on violations.
3. **EXECUTION PLANE (Workers / Scouts / Verifiers / Reviewers):** Leaf execution subagents.

### C. Delegation Prohibitions
1. **Worker-to-Worker Delegation Forbidden:** Subagents MUST NOT delegate tasks to other subagents.
2. **Subagent Spawning Forbidden:** Subagents (`SCOUT`, `STANDARD_WORKER`, `DEEP_WORKER`, `VERIFIER`, `PREMIUM_SECOND_OPINION`) MUST NOT spawn child agents.
3. **Peer Messaging Forbidden:** Subagents MUST NOT communicate directly with peer subagents.
4. **Root Controller Must Not Self-Promote (`ROOT_CONTROLLER_MUST_NOT_SELF_PROMOTE`):** The Root Controller MUST NOT independently plan, decompose, choose models/efforts, choose verifiers, or decide task completion.
5. **Dedicated Boss Mandatory (`DEDICATED_BOSS_REQUIRED`):** If the Skill-bound Boss cannot be bound on the required model/effort, the mission MUST fail closed with `BOSS_BINDING_UNAVAILABLE`. The Root Controller MUST NOT take over as Boss.
6. **Dedicated Boss Continuity Required (`DEDICATED_BOSS_CONTINUITY_REQUIRED`):** The same Boss child instance MUST be maintained across the entire mission via child follow-up tasks. Re-spawning a new Boss per turn is forbidden.
7. **No Implementer Self-Verification:** The implementer of a task is strictly forbidden from verifying its own work.

---

## 2. Source of Truth & Evidence Precedence

When evaluating system state, capabilities, or configuration, the following strict precedence hierarchy applies:
```text
1. FRESH LIVE RUNTIME EVIDENCE       (Live CLI / tool execution results from active mission)
2. ACTIVE CONFIG / AGENT TOML        (Active ~/.codex/*.toml and ~/.codex/agents/*.toml)
3. CANONICAL SHARED CORE POLICY      (Normative rules in ORCHESTRATOR_CORE.md)
4. HISTORICAL PROOF / METADATA LOGS  (Router logs, multi-agent settings, static proof files)
```
- Stale historical metadata or disabled markers in observational JSON files MUST NOT override successful live CLI execution.
- Shared Core policy defines intended architectural invariants, while live tool responses define current operational provider availability.

---

## 3. Skill Boss Bindings & Provider-Qualified Endpoint Registry

### A. Skill Boss Bindings
```yaml
skill_boss_bindings:
  grok-orchestrator-v2:
    required_boss_endpoint: GROK_4_6_HIGH
    model: nine-router/gcli/grok-4.6-high
    effort: high
    dedicated_boss_required: true

  sol-luna-orchestrator-v2:
    required_boss_endpoint: SOL_HIGH
    model: gpt-5.6-sol
    effort: high
    dedicated_boss_required: true
```

### B. Capability & Effort Evidence Model
Effort capability is normatively classified into two distinct dimensions:
- **`accepted_efforts`:** Reasoning effort parameters accepted by the upstream provider API without request rejection.
- **`effective_effort_status`:**
  - `PROVEN`: Audited and confirmed that distinct effort parameters produce measurable reasoning depth differences.
  - `ACCEPTED_BUT_EFFECTIVE_UNKNOWN`: Parameter accepted by provider, but upstream effective reasoning differentiation is unverified.

### C. Registry
```yaml
routing_policy: INITIAL_RELEASE_RC3

endpoints:
  - id: SOL_HIGH
    capacity_domain: openai_plus_capacity
    transport_domain: openai_native
    provider_route: openai
    model: gpt-5.6-sol
    accepted_efforts: [low, medium, high, xhigh, max, ultra]
    effective_effort_status: PROVEN
    candidate_roles: [boss]

  - id: PLUS_LUNA
    family: luna
    capacity_domain: openai_plus_capacity
    transport_domain: openai_native
    provider_route: openai
    model: gpt-5.6-luna
    agent_type: luna_max_worker
    accepted_efforts: [low, medium, high, max]
    effective_effort_status: PROVEN # Native OpenAI reasoning parameter differentiation verified

  - id: GEMINI_FLASH_HIGH
    capacity_domain: google_ag_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/ag
    model: nine-router/ag/gemini-3.7-flash-high
    agent_type: router_nine_router_ag_gemini_3_7_flash_high
    accepted_efforts: [low, high, max]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN

  - id: DEEPSEEK_FLASH
    capacity_domain: opencode_go_capacity
    transport_domain: nine_router_transport
    provider_route: opencode-go
    model: opencode-go/deepseek-v4-flash
    agent_type: router_opencode_go_deepseek_v4_flash
    accepted_efforts: [low, high, max]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN

  - id: DEEPSEEK_PRO
    capacity_domain: opencode_go_capacity
    transport_domain: nine_router_transport
    provider_route: opencode-go
    model: opencode-go/deepseek-v4-pro
    agent_type: router_opencode_go_deepseek_v4_pro
    accepted_efforts: [high, max]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN

  - id: OCG_LUNA
    family: luna
    capacity_domain: opencode_go_capacity
    transport_domain: opencode_go_responses
    provider_route: opencode-go-responses
    model: opencode-go-responses/gpt-5.6-luna
    agent_type: router_opencode_go_responses_gpt_5_6_luna
    accepted_efforts: [high, max]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    policy_max_effort: high

  - id: OPUS_4_6_THINKING # Premium second-opinion reviewer only
    capacity_domain: claude_opus_ag_capacity # CAPACITY_RELATION_UNKNOWN to google_ag_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/ag
    model: nine-router/ag/claude-opus-4-6-thinking
    agent_type: router_nine_router_ag_claude_opus_4_6_thinking
    accepted_efforts: [low, high, max]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    normal_routing_member: false
    role: PREMIUM_SECOND_OPINION
    access: READ_ONLY
    write_ownership: NONE

  - id: GROK_4_6_HIGH # Metadata candidate & Grok Boss Profile
    capacity_domain: xai_gcli_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/gcli
    model: nine-router/gcli/grok-4.6-high
    accepted_efforts: [high, max]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    candidate_roles: [boss, deep_worker]
```

### D. Operational Capacity vs. Architecture
- `ARCHITECTURAL_CORRECTNESS` (the normative validity of chains and safety invariants) is strictly decoupled from `CURRENT_PROVIDER_AVAILABILITY` (transient quotas or outages).
- Temporary hard exhaustion of `openai_plus_capacity` or other domains is handled via mission-scoped health breakers; it does not alter normative routing design.

---

## 4. Logical Roles & Initial Release Routing (Option A — Deterministic)

```yaml
role_chains:
  SCOUT: # Strictly Read-Only; High reasoning for robust discovery, conserves Plus
    - attempt: 1
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 2
      endpoint: DEEPSEEK_FLASH
      model: opencode-go/deepseek-v4-flash
      effort: high
    - attempt: 3
      endpoint: PLUS_LUNA
      model: gpt-5.6-luna
      effort: medium

  STANDARD_WORKER: # Routine implementation with High reasoning; DeepSeek Flash fallback
    - attempt: 1
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 2
      endpoint: PLUS_LUNA
      model: gpt-5.6-luna
      effort: max
    - attempt: 3
      endpoint: DEEPSEEK_FLASH
      model: opencode-go/deepseek-v4-flash
      effort: high

  DEEP_WORKER: # Maximum analytical & algorithmic depth
    - attempt: 1
      endpoint: DEEPSEEK_PRO
      model: opencode-go/deepseek-v4-pro
      effort: max
    - attempt: 2
      endpoint: PLUS_LUNA
      model: gpt-5.6-luna
      effort: max
    - attempt: 3
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: max
```

*Operational Note (Post-Initial Release Candidate):* A Gemini-heavier routing distribution (Option B) is documented as an alternative for environments experiencing frequent OpenAI Plus quota exhaustion.

---

## 5. Packet Architecture, Protocol & Validation (Normative Contracts)

### A. Context & Isolation Invariant (`EXPLICIT_PACKET_ONLY`)
All delegated subagents (`SCOUT`, `STANDARD_WORKER`, `DEEP_WORKER`, `VERIFIER`, `PREMIUM_SECOND_OPINION`) execute with `fork_turns="none"`. Context isolation is 100% self-contained. The Boss MUST transport all required context through explicit packet fields and MUST NOT rely on inherited parent history.

### B. Private Reasoning Prohibition
Packets MUST NOT require or transport private hidden reasoning or raw chain-of-thought traces. Communication across agents is strictly restricted to factual summaries, decisions, findings, evidence, assumptions, and required corrections.

### C. Boss-Controller Protocol Schemas (v1)

#### 1. BOSS_MISSION_PACKET (Controller -> Dedicated Boss)
```yaml
BOSS_MISSION_PACKET:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Unique mission identifier (e.g. mission-1787106000)
  user_goal: string                       # Original verbatim user objective
  skill_invoked: string                   # Name of skill invoked (e.g. grok-orchestrator-v2)
  workspace_root: string                  # Canonical absolute workspace root path
  environment_summary: string             # Factual environment facts (OS, tools available)
  constraints: [string]                   # Global mission constraints
```

#### 2. BOSS_ACTION_PACKET (Dedicated Boss -> Controller)
```yaml
BOSS_ACTION_PACKET:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Retained mission identifier
  action_id: string                       # Unique action ID (e.g. act-1)
  action: string                          # SPAWN_CHILD | MISSION_COMPLETE | MISSION_BLOCKED | REWORK_REQUIRED
  logical_task_id: string                 # Logical task ID within mission
  role: string                            # SCOUT | STANDARD_WORKER | DEEP_WORKER | VERIFIER | PREMIUM_SECOND_OPINION
  requested_endpoint: string              # Exact endpoint ID from registry (e.g. GEMINI_FLASH_HIGH, PLUS_LUNA)
  requested_model: string                 # Canonical model string
  requested_effort: string                # low | medium | high | max
  fork_turns: string                      # MUST be "none"
  owned_files: [string]                   # Authorized write targets (disjoint)
  forbidden_files: [string]               # Explicit prohibited paths
  task_packet: object                     # WORKER_TASK_PACKET or VERIFICATION_PACKET
  verification_required: boolean          # true for write-capable tasks
  expected_result_contract: string        # Clear deliverable contract
```

#### 3. CHILD_EXECUTION_RESULT (Controller Execution Evidence -> Controller Internal)
```yaml
CHILD_EXECUTION_RESULT:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Retained mission identifier
  action_id: string                       # Matches BOSS_ACTION_PACKET action_id
  logical_task_id: string                 # Matches logical_task_id
  child_id: string                        # Actual child agent task_name / ID
  agent_type: string                      # Actual agent_type used for spawn
  actual_model: string                    # Observable actual model or UNPROVEN
  actual_effort: string                   # Observable actual effort or UNPROVEN
  status: string                          # SUCCESS | FAILED | INTERRUPTED | ERROR
  mutation_state: string                  # NONE | COMMITTED | PARTIAL | UNKNOWN
  artifacts: [string]                     # Generated/modified file paths
  test_evidence: string                   # Factual test logs / outputs
  output_summary: string                  # Factual output from child
  errors: [string]                        # Error messages if failed
```

#### 4. BOSS_FOLLOWUP_PACKET (Controller -> Dedicated Boss)
```yaml
BOSS_FOLLOWUP_PACKET:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Retained mission identifier
  child_result: object                    # Lossless CHILD_EXECUTION_RESULT
  controller_status: string               # READY_FOR_NEXT_ACTION | REJECTION
  rejection_reason: string                # Populated only if Boss action was rejected by Controller
```

#### 5. FINAL_BOSS_DECISION (Dedicated Boss -> Controller)
```yaml
FINAL_BOSS_DECISION:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Retained mission identifier
  decision: string                        # COMPLETE | INCOMPLETE | BLOCKED | REWORK_REQUIRED
  summary: string                         # Factual mission summary
  completed_tasks: [string]               # List of verified logical task IDs
  unverified_tasks: [string]              # List of unverified task IDs
  rework_notes: string                    # Rework requirements if decision is REWORK_REQUIRED
```

### D. WORKER_TASK_PACKET Schema (v1)
```yaml
WORKER_TASK_PACKET:
  packet_version: 1                       # Integer schema version (1 for RC2)
  logical_task_id: string                 # Unique task ID within mission; retained across fallbacks and rework
  role: SCOUT | STANDARD_WORKER | DEEP_WORKER  # Logical role matching Section 4
  objective: string                       # Concrete outcome to achieve (not just files to inspect)
  scope: string                           # Explicit subsystem, files, or problem boundary (no silent widening)
  owned_files: [string]                   # Explicit files/directories worker is authorized to modify (if write_allowed=true)
  forbidden_files: [string]               # Explicit paths worker MUST NOT modify
  write_allowed: boolean                  # false for SCOUT/VERIFIER/PREMIUM_SECOND_OPINION; true only for implementers on owned_files
  relevant_context: string                # Factual task-relevant context only (no arbitrary conversation dump)
  constraints: [string]                   # Mandatory technical, safety, or compatibility constraints
  expected_output: string                 # Required deliverable (e.g. findings report, patch, test evidence)
  validation: [string]                    # Required verification commands or checks worker must run
  done_when: string                       # Objective completion criteria
  verification_required: boolean          # true for all write-capable implementation tasks
  parent_assumptions: [string]            # Explicit assumptions Boss relies on (distinguishable from facts; challengeable)
```

### E. Worker Packet Validation Rule (`PACKET_INVALID`)
Before spawning any worker, the Boss MUST validate that all mandatory fields are present and coherent:
- If `write_allowed: true` but `owned_files` is empty or missing $\rightarrow$ `PACKET_INVALID`.
- If `objective`, `scope`, `role`, `expected_output`, or `done_when` is missing $\rightarrow$ `PACKET_INVALID`.
- **Pre-Execution Invariant:** `PACKET_INVALID` occurs before worker dispatch. The Boss MUST NOT spawn the worker and MUST NOT trigger provider/endpoint fallback. Packet validation failure is a parent contract defect, not a provider failure.

---

### F. VERIFICATION_PACKET Schema (v1)
```yaml
VERIFICATION_PACKET:
  packet_version: 1                       # Integer schema version (1 for RC2)
  logical_task_id: string                 # Matches the logical_task_id of the implementation
  implementation_completed_by: string     # Exact endpoint ID that performed implementation (e.g. PLUS_LUNA, GEMINI_FLASH_HIGH)
  requirements: string                    # Objective specifications against which work must be evaluated
  scope: string                           # Boundary of the verified work
  artifacts_to_inspect: [string]          # Modified files, generated assets, diffs, or logs to inspect
  allowed_read_paths: [string]            # Read-accessible paths
  forbidden_write_paths: [string]         # All paths (Verifier is strictly read-only; write_allowed=false)
  tests_or_checks: [string]               # Verification commands, automated test suites, or reproduction steps to run
  acceptance_criteria: [string]           # Clear pass/fail criteria
  known_environment_constraints: [string] # Runtime or environmental constraints
  evidence_required: [string]             # Required factual evidence (e.g. test outputs, citations of line numbers)
  implementer_reasoning_included: false   # MUST be false (no implementer rationalizations or persuasive narrative)
```

### G. Verification Packet Independence Invariant (`VERIFICATION_PACKET_INDEPENDENCE`)
The `VERIFICATION_PACKET` MUST NOT contain:
- The implementer's private reasoning, self-justifications, or narrative arguments ("I made this change because...").
- Biasing claims such as "the implementation is verified correct; please confirm".
- Any request to rubber-stamp the previous worker's output.

The `VERIFICATION_PACKET` MAY contain:
- Factual artifacts: modified files, unified diffs, test logs, reproduction commands, and formal acceptance criteria.

Verifier Access: `write_allowed: false`. Verifiers must never attempt in-place repairs. If defects are found, the verifier reports blocking findings to the Boss to initiate structured rework.

---

### H. Structured Rework Contract (`prior_attempt_summary`)
When an implementation fails verification or tests, the Boss initiates controlled rework using a fresh `WORKER_TASK_PACKET` containing a structured `prior_attempt_summary`:

```yaml
prior_attempt_summary:
  logical_task_id: string                 # Retained logical task ID
  previous_attempt:
    completed_by: string                  # Endpoint ID of the prior implementer
    result: string                        # Factual summary of the prior attempt outcome
    files_changed: [string]               # Exact list of files touched
    validation_performed: [string]        # Checks run by the prior worker
  verifier_findings: [string]             # Factual findings reported by independent verifier
  blocking_defects: [string]              # Specific defects requiring correction
  required_correction: string             # Clear corrective instructions for the rework attempt
  unchanged_constraints: [string]         # Persistent constraints that remain in effect
```

### I. Rework Lifecycle & Ownership Preservation Invariant
```text
Worker Attempt
  → Independent Verifier [BLOCK]
  → Boss generates prior_attempt_summary
  → Corrective WORKER_TASK_PACKET (fork_turns="none", same logical_task_id, preserved owned_files)
  → Corrective Worker
  → Independent Verifier [PASS]
  → Boss Integration
```
- The corrective worker receives the `prior_attempt_summary` inside `relevant_context` or dedicated packet fields.
- Rework packets MUST NOT pass full conversation history or previous worker reasoning traces.
- Ownership boundaries (`owned_files`, `forbidden_files`) are strictly preserved across rework cycles unless the Boss explicitly documents a scope expansion.

---

## 6. Implementer-Aware Independent Verification & Exhaustion Policy

### A. Fundamental Invariant
```text
IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK
(verifier.endpoint_id != task.completed_by.endpoint_id)
```
Every verifier must execute with `fork_turns="none"` and an independent `VERIFICATION_PACKET`.

### B. Authoritative Implementer-Aware Verifier Routing & Chains

```yaml
verifier_chains:
  GEMINI_FLASH_HIGH:
    - attempt: 1
      endpoint: PLUS_LUNA
      model: gpt-5.6-luna
      effort: max
    - attempt: 2
      endpoint: OCG_LUNA
      model: opencode-go-responses/gpt-5.6-luna
      effort: high

  PLUS_LUNA:
    - attempt: 1
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 2
      endpoint: DEEPSEEK_PRO
      model: opencode-go/deepseek-v4-pro
      effort: high

  OCG_LUNA:
    - attempt: 1
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 2
      endpoint: DEEPSEEK_PRO
      model: opencode-go/deepseek-v4-pro
      effort: high

  DEEPSEEK_PRO:
    - attempt: 1
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 2
      endpoint: PLUS_LUNA
      model: gpt-5.6-luna
      effort: max
    - attempt: 3
      endpoint: OCG_LUNA
      model: opencode-go-responses/gpt-5.6-luna
      effort: high

  DEEPSEEK_FLASH:
    - attempt: 1
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 2
      endpoint: PLUS_LUNA
      model: gpt-5.6-luna
      effort: max
    - attempt: 3
      endpoint: OCG_LUNA
      model: opencode-go-responses/gpt-5.6-luna
      effort: high
```

#### Verifier Independence & Filtering Invariants:
1. **Exact Implementer Self-Conflict:** A verifier endpoint must never verify its own implementation (e.g. `GEMINI_FLASH_HIGH` cannot verify `GEMINI_FLASH_HIGH`).
2. **Luna Model-Family Conflict:** `PLUS_LUNA` and `OCG_LUNA` share the same underlying model family (`gpt-5.6-luna`). Therefore, `PLUS_LUNA` implementations CANNOT be verified by `OCG_LUNA`, and `OCG_LUNA` implementations CANNOT be verified by `PLUS_LUNA`.
3. **DeepSeek Pro Scope:** `DEEPSEEK_PRO` is reserved primarily for deep worker implementations and specific non-Gemini verifier fallback. It is NOT the normal verifier fallback for `GEMINI_FLASH_HIGH` work.
4. **Effort Caps:** `OCG_LUNA` has `policy_max_effort: high`, so verifier attempts for `OCG_LUNA` are capped at `high`. `PLUS_LUNA` verifier attempts execute at `max`.

*Skip semantics:* `SKIPPED_IMPLEMENTER_CONFLICT` and `SKIPPED_HEALTH_SUPPRESSED` do **NOT** consume an attempt number.

### C. Verifier Chain Exhaustion Invariant (`VERIFIER_CHAIN_EXHAUSTED`)
If all candidate verifiers in the base pool are skipped due to implementer conflict or health suppression:
1. The verification outcome reason becomes `VERIFIER_CHAIN_EXHAUSTED`.
2. The task state remains `INCOMPLETE`.
3. The Boss MUST report `TASK_UNVERIFIED_DUE_TO_VERIFIER_EXHAUSTION` to the user.
4. **Absolute Prohibition:** Under NO circumstances may the implementer be used to self-verify to escape verifier exhaustion. The task MUST NOT be marked `COMPLETE`.
---

## 7. Runtime Mission Trace Specification

To provide complete, auditable operational observability, every mission writes a durable Mission Trace to `~/.codex/orchestrator-traces/<mission_id>.json`.

### A. Trace Schema (v1)
```yaml
mission:
  mission_id: string
  started_at: string                      # ISO-8601 UTC
  skill: string                           # grok-orchestrator-v2 | sol-luna-orchestrator-v2
  status: string                          # IN_PROGRESS | COMPLETE | INCOMPLETE | BLOCKED

controller:
  actual_session_model: string            # Observable session model (or UNPROVEN)
  role: "ROOT_CONTROLLER"

boss:
  required_endpoint: string               # GROK_4_6_HIGH | SOL_HIGH
  requested_model: string                 # Canonical model string
  requested_effort: string                # high
  child_id: string                        # Actual task_name of Boss child
  actual_agent_type: string               # Agent type used
  actual_model: string                    # Observable actual model (or UNPROVEN)
  actual_effort: string                   # Observable actual effort (or UNPROVEN)
  binding_proven: boolean                 # true only if runtime evidence confirms model
  continuity_proven: boolean              # true only if multi-turn continuity confirmed

actions:
  - action_id: string
    logical_task_id: string
    role: string
    boss_requested: { endpoint: string, model: string, effort: string }
    controller_validation: { result: string, reason: string } # VALID | REJECTED
    controller_executed: { child_id: string, agent_type: string, actual_model: string, actual_effort: string }
    binding_match: boolean
    result: { status: string, mutation_state: string, errors: [string] }

verification:
  implementer: string
  verifier: string
  independent: boolean
  model_family_independent: boolean
  result: string # PASS | BLOCK | UNVERIFIED

rework:
  count: integer

final:
  boss_decision: string                   # COMPLETE | INCOMPLETE | BLOCKED | REWORK_REQUIRED
  mission_result: string                  # Final user status
```

### B. Trace Security & Privacy Invariant
Mission traces MUST NOT store API keys, auth headers, passwords, secrets, private reasoning traces, or full verbatim conversation dumps. Only structured operational metadata, task contracts, identifiers, and factual evidence are recorded.

### C. Unproven Evidence Handling
If an actual runtime field cannot be verified from live events, it MUST be recorded as `UNPROVEN` (or `false` for boolean flags). Fabricating evidence is strictly prohibited.

---

## 8. Premium Second Opinion Contract (`OPUS_4_6_THINKING`)

- **Normative Read-Only Invariant (`PREMIUM_SECOND_OPINION_READ_ONLY`):** `OPUS_4_6_THINKING` when invoked as `PREMIUM_SECOND_OPINION` is strictly **READ-ONLY**. It receives `fork_turns="none"`, `access: read-only`, and `write_ownership: none`.
- **No Implementation Escape Hatch:** It MUST NOT modify, create, rename, or delete files, and MUST NOT execute mutating commands. If a defect or correction is required, findings return to the Boss to dispatch an authorized write worker under standard ownership rules.
- **Not a Routine Member:** Opus is reserved exclusively for high-stakes decisions and is NOT a member of standard worker fallback chains.
- **Invocations Allowed Exclusively Under:**
  1. `CRITICAL_SECURITY_CHANGE`
  2. `RELEASE_CRITICAL_CHANGE`
  3. `ARCHITECTURE_CRITICAL_CHANGE`
  4. `NORMAL_VERIFIER_DISAGREEMENT`
  5. `REPEATED_REWORK_FAILURE`
  6. `BOSS_EXPLICITLY_REQUESTS_SECOND_OPINION`
  7. High-risk tasks completed by `GEMINI_FLASH_HIGH` requiring premium independent review.

---

## 9. Failure Classification & Fallback Safety Policy

Every failed attempt MUST be explicitly classified before determining next actions:

1. **`SAFE_PRE_EXECUTION_FAILURE`**: Failure occurred before task side effects began. Automatic fallback is **ALLOWED** for all roles.
2. **`SAFE_READ_ONLY_PROVIDER_FAILURE`**: Provider/transport failure (including 502 Bad Gateway / Empty Completion) on a **strictly read-only role (`SCOUT`, `VERIFIER`, `PREMIUM_SECOND_OPINION`)** where mutation evidence is `NONE`. Automatic fallback is **ALLOWED**.
3. **`AMBIGUOUS_EXECUTION_STATE`**: Mid-turn timeouts, connection drops during tool execution, or 502 with unknown mutation state on write-capable roles (`STANDARD_WORKER`, `DEEP_WORKER`). Automatic fallback is **FORBIDDEN**. Hold ownership, inspect files, and alert parent.
4. **`LOGIC_OR_TASK_FAILURE`**: Worker executed and returned but produced incorrect code, syntax errors, or failing tests. Automatic fallback is **FORBIDDEN**. Initiates structured rework.
5. **`UNKNOWN_FAILURE`**: Unclassified errors. Fail closed. Automatic fallback is **FORBIDDEN**.

---

## 10. Mission Health Ledger & Circuit Breaker Policy

- **Scopes:** `ENDPOINT` | `CAPACITY_DOMAIN` | `TRANSPORT_DOMAIN`.
- **States:** `ELIGIBLE` | `OPEN_FOR_MISSION` (Resets at start of new mission in memory; no persistent on-disk ledger).
- **Hard Quota Exhaustion (403/Usage Limit):** Suppresses `CAPACITY_DOMAIN` for active mission.
- **Model 404/Unavailable:** Suppresses `ENDPOINT` only.
- **Gateway Connection Refused:** Suppresses `TRANSPORT_DOMAIN`.
- **Non-Breaker Events:** Temporary 429, 500/502/503/504, 502 Empty Completion, Timeouts, and Ambiguous Write States **NEVER** open a mission breaker.

---

## 11. Task Lifecycle & Terminal States

### A. Primary Task States
- **`COMPLETE`**: All requirements verified, tests pass, independent verifier returned PASS.
- **`INCOMPLETE`**: Task in progress or unverified (e.g. `VERIFIER_CHAIN_EXHAUSTED`, budget cap reached).
- **`BLOCKED`**: Unrecoverable defect reached after max rework attempts or unresolvable environment defect.

### B. Outcome & Reason Codes
- `PACKET_INVALID`: Pre-dispatch schema error; worker not spawned; no provider fallback.
- `VERIFIER_CHAIN_EXHAUSTED`: Independent verification unavailable; task remains `INCOMPLETE`.
- `AMBIGUOUS_EXECUTION_STATE`: Write-capable worker encountered mid-turn error; fail-closed.
- `LOGIC_OR_TASK_FAILURE`: Defect detected by verifier/tests; leads to structured rework or `BLOCKED`.
- `UNKNOWN_FAILURE`: Unclassified error; fail closed.

---

## 12. Wrapper Responsibilities & Core Boundary

- Both Sol-Luna (`sol-luna-orchestrator-v2`) and Grok (`grok-orchestrator-v2`) wrappers are strictly thin consumers.
- **Wrapper Duties:**
  1. Define parent identity (`gpt-5.6-sol` / `nine-router/gcli/grok-4.6-high`) and config binding.
  2. Enforce fail-closed core loading (`ORCHESTRATION_CORE_CONFIGURATION_FAILURE`).
  3. Dispatch subagents using Section 5 packet contracts with `fork_turns="none"`.
- **No Wrapper Deviations:** All routing, skip tables, packet schemas, and safety invariants live exclusively in this Shared Core.
