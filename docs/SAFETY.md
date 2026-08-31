# Multi Orchestrator — Safety Invariants & Failure Taxonomy

## 1. Safety Invariants

### A. Strict Disjoint Write Ownership
- A worker assigned `write_allowed: true` receives an explicit list of `owned_files`.
- The worker is strictly prohibited from touching `forbidden_files` or modifying unassigned project paths.
- The Controller refuses protocol requests with overlapping write assignments; this does not authorize or sandbox native Host execution.

### B. Independent Verification (`IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK`)
- The agent that performed an implementation is strictly forbidden from acting as its verifier.
- Verifiers are selected from deterministic, implementer-aware verifier routing chains defined in Core.
- `PLUS_LUNA` and `OCG_LUNA` share the same underlying model family (`gpt-5.6-luna`) and are strictly forbidden from verifying each other's implementations (`Luna-family conflict`).
- If all independent candidates are unavailable or suppressed, the task enters `VERIFIER_CHAIN_EXHAUSTED` and remains `INCOMPLETE`. Under no circumstances is self-verification allowed.

### C. Premium Reviewer Isolation (Opus 4.6 Thinking)
- `OPUS_4_6_THINKING` is reserved exclusively as a premium second-opinion reviewer (`role: PREMIUM_SECOND_OPINION`).
- It is strictly **READ-ONLY** (`write_ownership: NONE`, `fork_turns="none"`). It cannot create, edit, rename, or delete files, nor execute mutating commands.

### D. Ambiguous Write State Fail-Closed
- If a write-capable worker experiences a mid-turn drop, timeout, or 502 with uncertain mutation state (`AMBIGUOUS_EXECUTION_STATE`), automatic fallback is strictly forbidden.
- The Boss halts the task, and the Controller refuses further write-capable Host requests until manual or factual state inspection resolves the ambiguity.
### E. Explicit Native Host Model Binding
- After route selection, every Auto Team child is created with top-level `model`, `reasoning_effort`, and `fork_turns="none"` arguments on the native `spawn_agent` call.
- A missing schema field, rejected override, or unavailable/mismatched Host-returned identity produces `HOST_MODEL_BINDING_ERROR` and stops the mission.
- The Controller never substitutes the root/parent model, silently omits an override, or selects a post-spawn fallback to hide a binding failure.
- Requested and effective identities are recorded separately in Mission Trace as `MATCH`, `MISMATCH`, or `UNPROVEN`; native allocation remains `HOST_EXTERNAL`.
- Native `task_name` values are bare lowercase identifiers matching `^[a-z0-9_]+$`; invalid paths, hyphens, spaces, or uppercase names are rejected as `HOST_AGENT_NAME_INVALID` before submission.

---

## 2. Failure Classification Taxonomy
Every failed attempt is classified into one of five deterministic buckets:

1. **`SAFE_PRE_EXECUTION_FAILURE`**: Evidence establishes that failure occurred before task side effects began. The Controller may submit a provider-fallback request.
2. **`SAFE_READ_ONLY_PROVIDER_FAILURE`**: Transport or empty completion failure on read-only roles (`SCOUT`, `VERIFIER`, `PREMIUM_SECOND_OPINION`). Automatic fallback is ALLOWED.
3. **`AMBIGUOUS_EXECUTION_STATE`**: Mid-turn timeout or network drop during tool execution on write-capable roles. Automatic fallback is FORBIDDEN.
4. **`LOGIC_OR_TASK_FAILURE`**: Worker returned incorrect code, syntax errors, or failing tests. Automatic fallback is FORBIDDEN; triggers structured rework.
5. **`UNKNOWN_FAILURE`**: Unclassified error. Fail-closed; automatic fallback is FORBIDDEN.

---

## 3. Mission Health & Circuit Breaker Model
- Health is tracked per session in an in-memory ledger across three scopes: `ENDPOINT`, `CAPACITY_DOMAIN`, `TRANSPORT_DOMAIN`.
- **Hard Quota Exhaustion (403/Usage Limit):** Suppresses the entire `CAPACITY_DOMAIN` for the remainder of the mission.
- **Transient Errors (429, 500, 502, 503, 504, Timeouts):** Never open circuit breakers.

## 4. Host Enforcement Boundary

Fail-closed safety here means the Controller refuses protocol validation, Host request submission, fallback, or continuation. Native allocation and effective identity remain `HOST_EXTERNAL`; repository instructions do not intercept or authorize them. `PreToolUse Agent` is an optional guardrail, not a strict Host boundary. See the authoritative [Core Execution Boundary Model](../core/ORCHESTRATOR_CORE.md#execution-boundary-model-host_external--authoritative).
