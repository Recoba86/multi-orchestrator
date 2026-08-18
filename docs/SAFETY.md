# Orchestrator V2 — Safety Invariants & Failure Taxonomy

## 1. Safety Invariants

### A. Strict Disjoint Write Ownership
- A worker assigned `write_allowed: true` receives an explicit list of `owned_files`.
- The worker is strictly prohibited from touching `forbidden_files` or modifying unassigned project paths.
- Parallel write assignments across disjoint file sets are safe; overlapping writes are prevented by Boss pre-planning.

### B. Independent Verification (`IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK`)
- The agent that performed an implementation is strictly forbidden from acting as its verifier.
- Verifiers are selected from an implementer-aware candidate pool (`GEMINI_FLASH_HIGH`, `DEEPSEEK_PRO`, `PLUS_LUNA`).
- If all independent candidates are unavailable or suppressed, the task enters `VERIFIER_CHAIN_EXHAUSTED` and remains `INCOMPLETE`. Under no circumstances is self-verification allowed.

### C. Premium Reviewer Isolation (Opus 4.6 Thinking)
- `OPUS_4_6_THINKING` is reserved exclusively as a premium second-opinion reviewer (`role: PREMIUM_SECOND_OPINION`).
- It is strictly **READ-ONLY** (`write_ownership: NONE`, `fork_turns="none"`). It cannot create, edit, rename, or delete files, nor execute mutating commands.

### D. Ambiguous Write State Fail-Closed
- If a write-capable worker experiences a mid-turn drop, timeout, or 502 with uncertain mutation state (`AMBIGUOUS_EXECUTION_STATE`), automatic fallback is strictly forbidden.
- The Boss halts the task and requires manual or factual state inspection before any further writes are authorized.

---

## 2. Failure Classification Taxonomy
Every failed attempt is classified into one of five deterministic buckets:

1. **`SAFE_PRE_EXECUTION_FAILURE`**: Failure occurred before task execution or side effects began. Automatic provider fallback is ALLOWED.
2. **`SAFE_READ_ONLY_PROVIDER_FAILURE`**: Transport or empty completion failure on read-only roles (`SCOUT`, `VERIFIER`, `PREMIUM_SECOND_OPINION`). Automatic fallback is ALLOWED.
3. **`AMBIGUOUS_EXECUTION_STATE`**: Mid-turn timeout or network drop during tool execution on write-capable roles. Automatic fallback is FORBIDDEN.
4. **`LOGIC_OR_TASK_FAILURE`**: Worker returned incorrect code, syntax errors, or failing tests. Automatic fallback is FORBIDDEN; triggers structured rework.
5. **`UNKNOWN_FAILURE`**: Unclassified error. Fail-closed; automatic fallback is FORBIDDEN.

---

## 3. Mission Health & Circuit Breaker Model
- Health is tracked per session in an in-memory ledger across three scopes: `ENDPOINT`, `CAPACITY_DOMAIN`, `TRANSPORT_DOMAIN`.
- **Hard Quota Exhaustion (403/Usage Limit):** Suppresses the entire `CAPACITY_DOMAIN` for the remainder of the mission.
- **Transient Errors (429, 500, 502, 503, 504, Timeouts):** Never open circuit breakers.
