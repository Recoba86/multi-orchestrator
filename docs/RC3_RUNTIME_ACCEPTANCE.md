# Multi Orchestrator RC3 — Runtime Acceptance Checkpoint

- **Checkpoint Date:** 2026-08-20
- **Baseline Commit:** `c1cd71b8aa141a3bccf34c99ea797fbc734c1ff1`
- **Accepted Tag:** `rc3-runtime-accepted-2026-08-20`
- **Architecture Status:** ACCEPTED
- **Runtime Status:** READY_FOR_NORMAL_USE

---

## 1. Executive Summary

RC3 is accepted for normal use within the repository protocol boundary. Executed acceptance paths produced correlated session, rollout, filesystem, and transport evidence for request routing, observed child outcomes, independent verification, token telemetry, and same-Boss continuity.

Acceptance does not prove that repository policy intercepts or authorizes native Host allocation. True mid-flight provider failure after child/session creation remains untested; no known defect is established for that path.

---

## 2. Acceptance Matrix

| Capability / Invariant | Status | Evidence Level |
|---|---|---|
| Observed Dedicated Grok Boss Runtime Attribution (`nine-router/gcli/grok-4.6-high`) | **PROVEN** | Level 5 (Raw Provider / Session) |
| Root Controller / Dedicated Boss Plane Separation | **PROVEN** | Level 4 (Session Runtime) |
| Happy-Path Same-Boss Continuity | **PROVEN** | Level 4 (Session Runtime) |
| SCOUT Observed Routing & Execution (`GEMINI_FLASH_HIGH`) | **PROVEN** | Level 5 (Transport & Rollout) |
| STANDARD_WORKER Observed Primary Routing & Execution | **PROVEN** | Level 5 (Transport & Rollout) |
| Observed Bounded Filesystem Writes | **PROVEN** | Level 5 (Filesystem & Git Diff) |
| Implementer-Aware Independent Verifier Routing | **PROVEN** | Level 4 (Session & Contract) |
| Requested Context Isolation (`fork_turns="none"`) and Observed Session Metadata | **PROVEN** | Level 4 (Session Metadata) |
| Controller Mission / Workspace / Repository Identity Guard | **PROVEN** | Level 4 (Contract Guard) |
| Final Boss Identity Guard & Nonce Validation | **PROVEN** | Level 4 (Session & Trace) |
| Provider-Qualified Runtime Attribution (PLUS_LUNA vs OCG_LUNA) | **PROVEN** | Level 5 (Raw Provider & Session) |
| Per-Child Exact Token Telemetry from Session JSONL | **PROVEN** | Level 4 (Rollout `token_count`) |
| Health-Suppressed Secondary Worker Route Execution (`PLUS_LUNA` Candidate #2) | **PROVEN** | Level 5 (Transport & Rollout) |
| Health-Suppressed Secondary Verifier Route Execution (`DEEPSEEK_PRO` Candidate #2) | **PROVEN** | Level 5 (Transport & Rollout) |
| Same-Boss Continuity Across Health-Suppressed Secondary Selection | **PROVEN** | Level 4 (Session Continuity) |
| Failed Dispatch Attempt Preservation in Mission Trace | **PROVEN** | Level 4 (Trace & Ledger) |
| Production Cleanliness After Experiments | **PROVEN** | Level 5 (Git & Process Audit) |
| Deliberate Health-Suppressed Secondary Selection Before Child / Session Creation | **PROVEN** | Level 5 (Controller, Trace & Rollout) |
| True Provider Failure and Fallback Recovery | **UNPROVEN / UNTESTED** | No mid-flight provider-failure evidence |
| Native Host Tool Dispatch / Interception / Pre-Allocation Authorization | **OUT_OF_SCOPE** | `HOST_EXTERNAL` |
| All-Entry-Point Non-Bypassability | **UNPROVEN** | `HOST_EXTERNAL` |

---

## 3. Evidence-Derived Runtime Routing Reference

*Note: These records are observed runtime outcomes under RC3 Core policy. Deliberate health suppression selected secondary routes before child / session creation; it is not evidence of provider failure or fallback recovery, and it is not proof that the repository authorized native Host allocation:*

- **Dedicated Grok Boss:** `GROK_4_6_HIGH` (`nine-router/gcli/grok-4.6-high`, high) via `nine-router`.
- **Primary Worker:** `GEMINI_FLASH_HIGH` (`nine-router/ag/gemini-3.7-flash-high`, high).
- **Secondary Worker (Health-Suppressed Secondary Route):** `PLUS_LUNA` (`gpt-5.6-luna`, max) via native `openai`.
- **Implementer-Aware Independent Verifier:** `DEEPSEEK_PRO` (`opencode-go/deepseek-v4-pro`, high) via `codex-router` when implementer is `PLUS_LUNA` (preventing Luna family conflict with `OCG_LUNA`).

---

## 4. Observability & Telemetry Source of Truth

Forensic audits established the authoritative evidence hierarchy:
1. **Raw Provider Transport:** Router logs (`~/.codex/codex-router/router.log`) and upstream status.
2. **Session Runtime Metadata:** Rollout logs (`~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`).
3. **Internal State:** Database thread spawn edges (`~/.codex/state_5.sqlite`).
4. **Mission Trace:** Structured trace file (`~/.codex/orchestrator-traces/<mission_id>.json`).

Exact per-child token accounting is directly extractable from rollout `token_count` events (`last_token_usage` and `total_token_usage`).

---

## 5. Scope Boundaries & Closure Policy

- **Controller request-submission vs Mid-flight Failure:** Deliberate health suppression and request-path secondary selection were observed at the Controller request-submission / pre-child-creation boundary (`BEFORE_CHILD_CREATION`). This proves secondary selection and trace behavior only; true provider failure and fallback recovery remain **UNPROVEN / UNTESTED**.
- **Host Boundary:** `BEFORE_CHILD_CREATION` proves the observed Controller request path and trace state, not authoritative Host interception or authorization. Native allocation and resolved effective identity remain `HOST_EXTERNAL`; `PreToolUse Agent` is only an optional guardrail.
- **Future Strict Integration:** Certification requires an authoritative hook in every native Host spawn path, resolved effective identity, fail-closed validation before allocation, all-entry-point non-bypassability, and correlated request/allocation/session/transport evidence.
- **Closure Standard:** RC3 milestone is formally closed. No further architectural micro-patches or speculative scaffolding are permitted without new empirical execution failure evidence.
