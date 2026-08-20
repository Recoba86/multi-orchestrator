# Multi Orchestrator RC3 — Runtime Acceptance Checkpoint

- **Checkpoint Date:** 2026-08-20
- **Baseline Commit:** `131cc9393c6877976872fce052e9ed415b45f473`
- **Architecture Status:** ACCEPTED
- **Runtime Status:** READY_FOR_NORMAL_USE

---

## 1. Executive Summary

RC3 is accepted for normal use. All defined and executed RC3 acceptance paths passed under live execution. Pre-spawn / dispatch transport failure recovery, secondary route execution, independent verifier routing, token telemetry, and same-Boss continuity through error paths have been rigorously proven with raw session rollout and transport evidence.

True mid-flight provider failure after child/session creation remains untested; no known defect is established for that path.

---

## 2. Acceptance Matrix

| Capability / Invariant | Status | Evidence Level |
|---|---|---|
| Dedicated Grok Boss Binding (`nine-router/gcli/grok-4.6-high`) | **PROVEN** | Level 5 (Raw Provider / Session) |
| Root Controller / Dedicated Boss Plane Separation | **PROVEN** | Level 4 (Session Runtime) |
| Happy-Path Same-Boss Continuity | **PROVEN** | Level 4 (Session Runtime) |
| SCOUT Live Routing & Execution (`GEMINI_FLASH_HIGH`) | **PROVEN** | Level 5 (Transport & Rollout) |
| STANDARD_WORKER Primary Routing & Execution | **PROVEN** | Level 5 (Transport & Rollout) |
| Bounded Filesystem Write Isolation | **PROVEN** | Level 5 (Filesystem & Git Diff) |
| Implementer-Aware Independent Verifier Routing | **PROVEN** | Level 4 (Session & Contract) |
| Context Isolation (`fork_turns="none"`) | **PROVEN** | Level 4 (Session Metadata) |
| Mission / Workspace / Repository Identity Binding | **PROVEN** | Level 4 (Contract Guard) |
| Final Boss Identity Guard & Nonce Validation | **PROVEN** | Level 4 (Session & Trace) |
| Provider-Qualified Runtime Attribution (PLUS_LUNA vs OCG_LUNA) | **PROVEN** | Level 5 (Raw Provider & Session) |
| Per-Child Exact Token Telemetry from Session JSONL | **PROVEN** | Level 4 (Rollout `token_count`) |
| Secondary Worker Route Execution (`PLUS_LUNA` Candidate #2) | **PROVEN** | Level 5 (Transport & Rollout) |
| Secondary Verifier Route Execution (`DEEPSEEK_PRO` Candidate #2) | **PROVEN** | Level 5 (Transport & Rollout) |
| Same-Boss Continuity Across Forced Fallback | **PROVEN** | Level 4 (Session Continuity) |
| Pre-Spawn / Dispatch Failure Recovery | **PROVEN** | Level 4 (Controller & Trace) |
| Failed Dispatch Attempt Preservation in Mission Trace | **PROVEN** | Level 4 (Trace & Ledger) |
| Production Cleanliness After Experiments | **PROVEN** | Level 5 (Git & Process Audit) |
| True Mid-Flight Child Failure Recovery | **UNTESTED** | *No Known Defect* |

---

## 3. Evidence-Derived Runtime Routing Reference

*Note: These records represent factual acceptance outcomes under RC3 Core policy:*

- **Dedicated Grok Boss:** `GROK_4_6_HIGH` (`nine-router/gcli/grok-4.6-high`, high) via `nine-router`.
- **Primary Worker:** `GEMINI_FLASH_HIGH` (`nine-router/ag/gemini-3.7-flash-high`, high).
- **Secondary Worker (Fallback):** `PLUS_LUNA` (`gpt-5.6-luna`, max) via native `openai`.
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

- **Pre-spawn vs Mid-flight Failure:** The verified failure recovery path operates at the dispatch / pre-spawn boundary (`BEFORE_CHILD_CREATION`). Mid-flight failure during an active child turn remains untested.
- **Closure Standard:** RC3 milestone is formally closed. No further architectural micro-patches or speculative scaffolding are permitted without new empirical execution failure evidence.
