# Shared Orchestrator Core (Normative RC3 Architecture — Skill-Bound Dedicated Boss)

This document defines the normative, engine-agnostic orchestration policy, execution boundary, skill-to-boss bindings, endpoint registry, role routing, packet contracts, failure-handling rules, mission-scoped health circuit breakers, implementer-aware independent verification, strict reviewer isolation, and runtime mission tracing for Release Candidate 3 (RC3).

---

## 0. Canonical Mission Identity & Isolation Invariants

Every orchestration mission is strictly bound to an immutable `MISSION_IDENTITY`:
```yaml
MISSION_IDENTITY:
  mission_id: string                      # Unique identifier per Skill invocation (e.g. mission-1787106000)
  skill: string                           # Name of invoked skill (autoteam; legacy wrapper names retained only for rollback)
  workspace_root: string                  # Canonical requested absolute workspace directory
  git_toplevel: string                    # Output of `git rev-parse --show-toplevel`
  repository_identity: string             # Remote repository URL or stable local repo name
  starting_branch: string                 # Starting branch (e.g. develop, main)
  starting_sha: string                    # Starting commit SHA
  boss_child_id: string                   # Dedicated Boss agent task_name bound exclusively to this mission
```

### Core Isolation Invariants:
1. **`NEW_MISSION_REQUIRES_FRESH_MISSION_ID`:** Every new invocation of an orchestrator Skill MUST generate a fresh, globally unique `mission_id`.
2. **`NEW_MISSION_REQUIRES_FRESH_DEDICATED_BOSS`:** For every new mission, the Controller MUST submit a request for a fresh Dedicated Boss and MUST NOT continue until the external Host returns a distinct child identity.
3. **`BOSS_REUSE_ACROSS_DISTINCT_MISSIONS_FORBIDDEN`:** A Boss child instance created for mission A MUST NOT be reused, referenced, or sent follow-up tasks in mission B.
4. **`TARGET_WORKSPACE_BINDING_REQUIRED`:** The Controller MUST verify workspace preflight (`pwd`, `git rev-parse --show-toplevel`, `git branch --show-current`, `git rev-parse HEAD`, `git remote get-url origin`). If `workspace_root != git_toplevel`, the mission fails closed with `TARGET_WORKSPACE_MISMATCH`.
5. **`MISSION_IDENTITY_MUST_MATCH_ON_EVERY_ACTION`:** Every `BOSS_ACTION_PACKET` emitted by the Boss MUST match the `mission_id`, `workspace_root`, and `repository_identity` of the active `MISSION_IDENTITY`. Mismatches fail closed with `MISSION_CONTEXT_MISMATCH`.
6. **`MISSION_IDENTITY_MUST_MATCH_ON_EVERY_FOLLOWUP`:** Every `BOSS_FOLLOWUP_PACKET` delivered to the Boss MUST match `mission_id`, `workspace_root`, `repository_identity`, and `boss_child_id`. Mismatches fail closed with `MISSION_CONTEXT_MISMATCH`.
7. **`MISSION_CONTEXT_MISMATCH_FAIL_CLOSED`:** Any context mismatch in mission ID, workspace root, repository identity, or Boss child ID makes protocol validation fail; the Controller MUST NOT submit that Host request, attempt provider fallback, or take over as Boss.
8. **`FORK_TURNS_NONE_REQUIRED`:** Every Controller-submitted child request (`DEDICATED_BOSS`, `SCOUT`, `STANDARD_WORKER`, `DEEP_WORKER`, `VERIFIER`, `PREMIUM_SECOND_OPINION`) MUST explicitly request `fork_turns="none"`. Omitting it, setting `fork_turns="all"`, or using any other value is invalid and the Controller MUST refuse submission with `FORK_TURNS_POLICY_VIOLATION`.
9. **`HOST_MODEL_BINDING_REQUIRED`:** Every Auto Team child request MUST explicitly carry the validated `model` and `reasoning_effort` as native Host spawn arguments. A missing, rejected, unavailable, or mismatched binding fails closed with `HOST_MODEL_BINDING_ERROR`.

### Execution Boundary Model (`HOST_EXTERNAL`) — Authoritative

The repository controls the orchestration protocol, not Codex native allocation:

- **Repository / Controller boundary:** Core defines packet, policy, identity, routing and selection rules, and verifier-assignment rules; the Boss selects within those rules, and the Controller validates the selections, chooses whether to call the native spawn tool, submits the validated request, relays Host-returned results, and records trace/evidence. A fail-closed rule means the Controller refuses protocol validation, Host request submission, or further protocol continuation.
- **`HOST_EXTERNAL` boundary:** The Codex Host owns native spawn and host-tool dispatch/interception, child allocation, final effective agent/model/effort identity, context construction, lifecycle, and admission across every native entry point. Repository Markdown, skills, traces, and validators do not execute, intercept, or authorize that allocation.
- **Auto Team binding contract:** After route selection and validation, the Controller MUST call native `spawn_agent` with top-level `model=<requested_model>`, `reasoning_effort=<requested_effort>`, and `fork_turns="none"`. Endpoint names, agent declarations, packet metadata, and prompt text do not bind a child model.
- **Binding failure contract:** If the effective `spawn_agent` schema lacks either override, the Host rejects either override, or returned child/session evidence does not match both requested values, the Controller MUST stop and report `HOST_MODEL_BINDING_ERROR`. It MUST NOT retry with parent/default inheritance, silently omit an override, submit a post-spawn fallback, or use a subprocess workaround.
- **Binding evidence:** For each child, the Mission Trace records the requested model/effort, Host-returned effective model/effort, and `MATCH`, `MISMATCH`, or `UNPROVEN`. A mismatch or unproven value prevents follow-up and mission continuation; the Host remains authoritative for the effective identity.
- **Current guarantee:** A conforming Controller does not submit a request that fails Core validation and does not treat requested configuration as proven effective runtime identity. Returned child/session/transport evidence may prove an observed allocation after the fact.
- **Explicit non-guarantees:** RC3 provides no repository guarantee of native Host tool interception or authorization. It does not prove pre-allocation Host authorization, effective-identity validation before allocation, or non-bypassability through native entry points outside this protocol. `PreToolUse Agent`, when available, is an optional guardrail only and is not the strict Host boundary.
- **Future strict integration:** Strict enforcement requires an authoritative mandatory Host hook directly in every native spawn path, resolution of the final effective identity, fail-closed validation before allocation, coverage that cannot be bypassed through any entry point, and correlated request/allocation/session/transport runtime evidence.

---

## 1. System Topology & Delegation Invariants

### A. Strict Hub-and-Spoke Invariant (`TOPOLOGY_HUB_AND_SPOKE_ONLY`)
The repository protocol defines a centralized Hub-and-Spoke topology:
```text
      User / Developer
             │
             ▼
       ROOT_CONTROLLER
 (Session Model / Control Plane)
             │
             ▼ (submits Host requests & relays)
       DEDICATED_BOSS
  (Auto Team policy: Sol, then Grok routes)
             │ (decisions / actions)
             ▼
       ROOT_CONTROLLER
             │ (protocol-validated Host requests)
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
1. **DECISION PLANE (Dedicated Skill-Bound Boss):** For `$autoteam`, the dedicated child is requested from the canonical BOSS chain beginning with Sol; legacy wrapper bindings remain available only when the master switch is explicitly OFF for rollback. The Boss is accepted only after matching Host-returned evidence and is responsible for task understanding, decomposition, role selection, verifier assignment, rework decisions, and task completion evaluation.
2. **CONTROL PLANE (Root Controller):** The model selected in the active session/UI. Responsible strictly for validating Boss actions against Core policy, submitting protocol-validated requests to the external Host, relaying Host-returned factual results without semantic mutation, managing mission trace persistence, and refusing invalid submissions or continuation.
3. **EXECUTION PLANE (Workers / Scouts / Verifiers / Reviewers):** Leaf execution subagents.

### C. Delegation Prohibitions
These are repository protocol and agent-instruction obligations. The Controller enforces them by refusing nonconforming request submission or continuation; native Host-wide enforcement is outside this repository's current boundary.
1. **Worker-to-Worker Delegation Forbidden:** Subagents MUST NOT delegate tasks to other subagents.
2. **Subagent Spawning Forbidden:** Subagents (`SCOUT`, `STANDARD_WORKER`, `DEEP_WORKER`, `VERIFIER`, `PREMIUM_SECOND_OPINION`) MUST NOT spawn child agents.
3. **Peer Messaging Forbidden:** Subagents MUST NOT communicate directly with peer subagents.
4. **Root Controller Must Not Self-Promote (`ROOT_CONTROLLER_MUST_NOT_SELF_PROMOTE`):** The Root Controller MUST NOT independently plan, decompose, choose models/efforts, choose verifiers, or decide task completion.
5. **Dedicated Boss Mandatory (`DEDICATED_BOSS_REQUIRED`):** If a matching Boss request cannot be submitted or Host-returned evidence does not establish the required child, the Controller MUST refuse protocol continuation with `BOSS_BINDING_UNAVAILABLE`. The Root Controller MUST NOT take over as Boss.
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
  autoteam:
    required_boss_endpoint: SOL_HIGH
    model: gpt-5.6-sol
    effort: high
    dedicated_boss_required: true

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
    family: sol
    capacity_domain: openai_plus_capacity
    transport_domain: openai_native
    provider_route: openai
    model: gpt-5.6-sol
    accepted_efforts: [high]
    effective_effort_status: PROVEN
    candidate_roles: [boss, deep_worker, verifier]

  - id: PLUS_LUNA
    family: luna
    capacity_domain: openai_plus_capacity
    transport_domain: openai_native
    provider_route: openai
    model: gpt-5.6-luna
    accepted_efforts: [max]
    effective_effort_status: PROVEN
    candidate_roles: [standard_worker]

  - id: PLUS_TERRA
    family: terra
    capacity_domain: openai_plus_capacity
    transport_domain: openai_native
    provider_route: openai
    model: gpt-5.6-terra
    accepted_efforts: [high]
    effective_effort_status: PROVEN
    candidate_roles: [premium_second_opinion]

  - id: GEMINI_FLASH_MEDIUM
    family: gemini
    capacity_domain: google_ag_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/ag
    model: nine-router/ag/gemini-3.7-flash-medium
    agent_type: router_nine_router_ag_gemini_3_7_flash_medium
    accepted_efforts: [medium]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    candidate_roles: [scout]

  - id: GEMINI_FLASH_HIGH
    family: gemini
    capacity_domain: google_ag_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/ag
    model: nine-router/ag/gemini-3.7-flash-high
    agent_type: router_nine_router_ag_gemini_3_7_flash_high
    accepted_efforts: [high]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    candidate_roles: [standard_worker, deep_worker, verifier]

  - id: QWEN_3_8_FLASH
    family: qwen
    capacity_domain: commandcode_capacity
    transport_domain: commandcode_transport
    provider_route: commandcode
    model: commandcode/qwen3.8-flash
    agent_type: commandcode_qwen3_8_flash
    accepted_efforts: [high]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    candidate_roles: [scout]

  - id: GROK_4_6_HIGH
    family: grok
    capacity_domain: xai_gcli_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/gcli
    model: nine-router/gcli/grok-4.6-high
    agent_type: router_nine_router_gcli_grok_4_6_high
    accepted_efforts: [high]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    candidate_roles: [boss, deep_worker, verifier]

  - id: GROK_CURSOR_HIGH
    family: grok
    capacity_domain: xai_cursor_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/cu
    model: nine-router/cu/cursor-grok-4.6-high
    agent_type: router_nine_router_cu_cursor_grok_4_6_high
    accepted_efforts: [high]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    candidate_roles: [boss]

  - id: OPUS_COMBO
    family: opus
    capacity_domain: claude_opus_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router
    model: nine-router/Opus
    agent_type: router_nine_router_opus
    accepted_efforts: [high]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
    role: PREMIUM_SECOND_OPINION
    access: READ_ONLY
    write_ownership: NONE
    candidate_roles: [verifier, premium_second_opinion]

  # Legacy endpoints remain registered for rollback and old validator fixtures;
  # none are members of the canonical Auto Team role chains above.
  - id: DEEPSEEK_FLASH
    family: deepseek
    capacity_domain: opencode_go_capacity
    transport_domain: nine_router_transport
    provider_route: opencode-go
    model: opencode-go/deepseek-v4-flash
    agent_type: router_opencode_go_deepseek_v4_flash
    accepted_efforts: [high]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN

  - id: DEEPSEEK_PRO
    family: deepseek
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

  - id: OPUS_4_6_THINKING
    family: opus
    capacity_domain: claude_opus_capacity
    transport_domain: nine_router_transport
    provider_route: nine-router/ag
    model: nine-router/ag/claude-opus-4-6-thinking
    agent_type: router_nine_router_ag_claude_opus_4_6_thinking
    accepted_efforts: [high]
    effective_effort_status: ACCEPTED_BUT_EFFECTIVE_UNKNOWN
```
### D. Operational Capacity vs. Architecture
- `ARCHITECTURAL_CORRECTNESS` (the normative validity of chains and safety invariants) is strictly decoupled from `CURRENT_PROVIDER_AVAILABILITY` (transient quotas or outages).
- Temporary hard exhaustion of `openai_plus_capacity` or other domains is handled via mission-scoped health breakers; it does not alter normative routing design.

---
## 4. Logical Roles & Canonical Auto Team Routing

```yaml
role_chains:
  BOSS: # Dedicated Auto Team Planner; ordered priority/failover
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: GROK_CURSOR_HIGH
      model: nine-router/cu/cursor-grok-4.6-high
      effort: high

  SCOUT: # Read-only discovery
    - attempt: 1
      endpoint: GEMINI_FLASH_MEDIUM
      model: nine-router/ag/gemini-3.7-flash-medium
      effort: medium
    - attempt: 2
      endpoint: QWEN_3_8_FLASH
      model: commandcode/qwen3.8-flash
      effort: high

  STANDARD_WORKER: # Bounded implementation
    - attempt: 1
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 2
      endpoint: PLUS_LUNA
      model: gpt-5.6-luna
      effort: max

  DEEP_WORKER: # Deep implementation and analysis
    - attempt: 1
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 2
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
    - attempt: 3
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high

  VERIFIER: # Candidate construction precedes implementer-family filtering
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 4
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high

  PREMIUM_SECOND_OPINION: # Escalation-only read-only review
    - attempt: 1
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 2
      endpoint: PLUS_TERRA
      model: gpt-5.6-terra
      effort: high
```

SolMode and GrokMode remain persistent operator state for compatibility,
status, and explicit activation/rollback commands. They do not select an
alternate model chain or silently replace this canonical Auto Team policy.

---

## 5. Packet Architecture, Protocol & Validation (Normative Contracts)

### A. Context & Isolation Invariant (`EXPLICIT_PACKET_ONLY`)
All Controller-submitted requests for delegated subagents (`SCOUT`, `STANDARD_WORKER`, `DEEP_WORKER`, `VERIFIER`, `PREMIUM_SECOND_OPINION`) specify `fork_turns="none"`. The Boss MUST make each packet self-contained and MUST NOT rely on inherited parent history. Actual Host context construction remains `HOST_EXTERNAL` and requires runtime evidence.

### B. Private Reasoning Prohibition
Packets MUST NOT require or transport private hidden reasoning or raw chain-of-thought traces. Communication across agents is strictly restricted to factual summaries, decisions, findings, evidence, assumptions, and required corrections.

### C. Boss-Controller Protocol Schemas (v1)

#### 1. BOSS_MISSION_PACKET (Controller -> Dedicated Boss)
```yaml
BOSS_MISSION_PACKET:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Unique mission identifier (e.g. mission-1787106000)
  skill_invoked: string                   # Name of skill invoked (e.g. grok-orchestrator-v2)
  workspace_root: string                  # Canonical absolute workspace root path
  git_toplevel: string                    # Actual git rev-parse --show-toplevel
  repository_identity: string             # Normalized repository remote or name
  starting_branch: string                 # Current branch
  starting_sha: string                    # Current commit HEAD SHA
  user_goal: string                       # Original verbatim user objective
  environment_summary: string             # Factual environment facts (OS, tools available)
  constraints: [string]                   # Global mission constraints
```

#### 2. BOSS_ACTION_PACKET (Dedicated Boss -> Controller)
```yaml
BOSS_ACTION_PACKET:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Retained mission identifier
  workspace_root: string                  # Retained workspace root
  repository_identity: string             # Retained repository identity
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

#### 3. CHILD_EXECUTION_RESULT (Host-Returned Execution Evidence -> Controller Internal)
```yaml
CHILD_EXECUTION_RESULT:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Retained mission identifier
  workspace_root: string                  # Retained workspace root
  repository_identity: string             # Retained repository identity
  action_id: string                       # Matches BOSS_ACTION_PACKET action_id
  logical_task_id: string                 # Matches logical_task_id
  child_id: string                        # Actual child agent task_name / ID
  agent_type: string                      # Host-returned agent_type observation
  requested_model: string                 # Model passed to native spawn_agent
  requested_effort: string                # Effort passed to native spawn_agent
  effective_model: string                 # Host-returned effective model or UNPROVEN
  effective_effort: string                # Host-returned effective effort or UNPROVEN
  binding_status: string                  # MATCH | MISMATCH | UNPROVEN
  actual_model: string                    # Compatibility alias for effective_model
  actual_effort: string                   # Compatibility alias for effective_effort
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
  workspace_root: string                  # Retained workspace root
  repository_identity: string             # Retained repository identity
  boss_child_id: string                   # Retained Boss child ID
  child_result: object                    # Lossless CHILD_EXECUTION_RESULT
  controller_status: string               # READY_FOR_NEXT_ACTION | REJECTION
  rejection_reason: string                # Populated only if Boss action was rejected by Controller
```

#### 5. FINAL_BOSS_DECISION (Dedicated Boss -> Controller)
```yaml
FINAL_BOSS_DECISION:
  packet_version: 1                       # Integer schema version
  mission_id: string                      # Retained mission identifier
  workspace_root: string                  # Retained workspace root
  repository_identity: string             # Retained repository identity
  boss_child_id: string                   # Retained Dedicated Boss child ID
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
Before the Controller submits any worker request to the Host, the Boss and Controller MUST validate that all mandatory fields are present and coherent:
- If `write_allowed: true` but `owned_files` is empty or missing $\rightarrow$ `PACKET_INVALID`.
- If `objective`, `scope`, `role`, `expected_output`, or `done_when` is missing $\rightarrow$ `PACKET_INVALID`.
- **Pre-Execution Invariant:** `PACKET_INVALID` occurs before Controller Host request submission. The Controller MUST NOT submit the worker request or a provider/endpoint fallback request. Packet validation failure is a parent contract defect, not a provider failure; this invariant makes no claim about Host allocations initiated outside this protocol.

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
Every verifier request must specify `fork_turns="none"` and an independent `VERIFICATION_PACKET`; Host context isolation remains `HOST_EXTERNAL`.

```yaml
verifier_chains:
  SOL_HIGH:
    - attempt: 1
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 2
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 3
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  GROK_4_6_HIGH:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 3
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  GROK_CURSOR_HIGH:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 3
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  GEMINI_FLASH_HIGH:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
  PLUS_LUNA:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 4
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  PLUS_TERRA:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 4
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  OPUS_COMBO:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  QWEN_3_8_FLASH:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 4
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  OCG_LUNA:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 4
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  DEEPSEEK_PRO:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 4
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
  DEEPSEEK_FLASH:
    - attempt: 1
      endpoint: SOL_HIGH
      model: gpt-5.6-sol
      effort: high
    - attempt: 2
      endpoint: GROK_4_6_HIGH
      model: nine-router/gcli/grok-4.6-high
      effort: high
    - attempt: 3
      endpoint: OPUS_COMBO
      model: nine-router/Opus
      effort: high
    - attempt: 4
      endpoint: GEMINI_FLASH_HIGH
      model: nine-router/ag/gemini-3.7-flash-high
      effort: high
```

#### Verifier Independence & Filtering Invariants:
1. **Exact Implementer Self-Conflict:** A verifier endpoint must never verify its own implementation (e.g. `GEMINI_FLASH_HIGH` cannot verify `GEMINI_FLASH_HIGH`).
2. **Cognitive-family independence:** Sol, Luna, and Terra are distinct GPT families; the two Grok routes share one Grok family; Gemini medium and high share one Gemini family.
3. **Ordered filtering:** Candidate construction follows the canonical verifier chain, then implementer-family exclusion, static eligibility, health eligibility, and primary-first selection.
4. **Premium second opinion:** `OPUS_COMBO` is attempted before `PLUS_TERRA`, and this escalation chain is separate from normal verifier dispatch.

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
  skill: string                           # autoteam; legacy wrapper names only for rollback
  status: string                          # IN_PROGRESS | COMPLETE | INCOMPLETE | BLOCKED

workspace:
  requested_workspace_root: string        # Requested workspace path
  actual_git_toplevel: string             # `git rev-parse --show-toplevel`
  repository_identity: string             # Remote URL or repo name
  branch_at_start: string                 # Current branch
  starting_sha: string                    # Current HEAD commit SHA
  identity_match: boolean                 # true if requested_workspace_root == actual_git_toplevel

controller:
  actual_session_model: string            # Observable session model (or UNPROVEN)
  role: "ROOT_CONTROLLER"

boss:
  required_endpoint: string               # SOL_HIGH | GROK_4_6_HIGH | GROK_CURSOR_HIGH
  requested_model: string                 # Canonical model string
  requested_effort: string                # high
  requested_fork_turns: string            # MUST be "none"
  child_id: string                        # Actual task_name of Boss child
  actual_agent_type: string               # Agent type used
  actual_model: string                    # Observable actual model (or UNPROVEN)
  actual_effort: string                   # Observable actual effort (or UNPROVEN)
  binding_proven: boolean                 # true only if runtime evidence confirms model
  continuity_proven: boolean              # true only if multi-turn continuity confirmed

actions:
  - action_id: string
    mission_id: string
    workspace_root: string
    repository_identity: string
    boss_child_id: string
    logical_task_id: string
    role: string
    boss_requested: { endpoint: string, model: string, effort: string, fork_turns: string }
    controller_validation: { result: string, reason: string } # VALID | REJECTED
    identity_validation: { mission_match: boolean, workspace_match: boolean, repository_match: boolean, boss_match: boolean, result: string } # VALID | REJECTED
    host_spawn_request: { tool: string, model: string, reasoning_effort: string, fork_turns: string } # Exact native arguments submitted by Controller
    controller_executed: { child_id: string, agent_type: string, effective_model: string, effective_effort: string, fork_turns: string } # Host-returned observation, not Controller-owned native execution
    context_isolation: { packet_only: boolean, requested_fork_turns: string, inherited_parent_turns: string } # inherited_parent_turns is UNPROVEN if unobservable
    binding: { requested_model: string, requested_effort: string, effective_model: string, effective_effort: string, status: string } # MATCH | MISMATCH | UNPROVEN
    binding_match: boolean                   # Compatibility projection of binding.status
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

- **Normative Read-Only Invariant (`PREMIUM_SECOND_OPINION_READ_ONLY`):** `OPUS_4_6_THINKING` when invoked as `PREMIUM_SECOND_OPINION` is strictly **READ-ONLY**. The Controller's request specifies `fork_turns="none"`, `access: read-only`, and `write_ownership: none`; Host enforcement remains `HOST_EXTERNAL`.
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

1. **`SAFE_PRE_EXECUTION_FAILURE`**: Evidence establishes that failure occurred before task side effects began. The Controller may submit a fallback request for all roles; this classification does not prove native Host interception before allocation.
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
- `PACKET_INVALID`: Pre-submission schema error; Controller submitted no worker or provider-fallback request.
- `HOST_MODEL_BINDING_ERROR`: Native `spawn_agent` cannot accept, bind, or prove the requested model/effort; no inherited/default-model retry or post-spawn fallback is permitted.
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
  3. Submit protocol-validated subagent requests to the external Host using Section 5 packet contracts with requested `fork_turns="none"`.
- **No Wrapper Deviations:** All routing, skip tables, packet schemas, and safety invariants live exclusively in this Shared Core.
