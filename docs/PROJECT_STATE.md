# Project State & Roadmap

## Current State: Release Candidate 4 (RC4) & Weighted Routing Activation — Validated

- **Checkpoint Date:** 2026-08-30
- **Baseline Commit:** `eb1ef834a4d916ee2cfee949959aa1c3f7c6bc93`
- **Prior Accepted Tags:** `rc3-runtime-accepted-2026-08-20`, `rc4-stable-promoted-2026-08-25`
- **Architecture Status:** ACCEPTED & EXTENDED (SolMode / GrokMode Mode-Aware Weighted Routing implemented & tested)
- **Runtime Status:** READY_FOR_NORMAL_USE (407 unit tests PASS, clean-room verification suite PASS)

### Key Architecture Deliverables
- **Dedicated Boss Architecture:** Completed and verified (Grok 4.6 High / Sol 5.6).
- **Root Controller & Dedicated Boss Plane Separation:** Strict protocol boundary with `fork_turns="none"`.
- **Implementer-Aware Independent Verification:** Non-self, model-family independent verification.
- **Mode-Aware Weighted Runtime Routing Subsystem:**
  - Persistent SolMode / GrokMode operator intent state (`~/.agents/runtime-routing/mode.json`) and CLI (`orchestrator-mode`).
  - Master activation switch with instant legacy rollback kill-switch (`orchestrator-routing`).
  - Pure deterministic weighted selector based on single SHA-256 cumulative bucket.
  - Failure-domain health cooldown tracking with auto-expiry.
  - Append-only routing telemetry and target-share report generation.
- **Mission Trace:** Integrated via `~/.codex/orchestrator-traces/<mission_id>.json` and CLI reader `mission-trace`.
- **Dynamic Verification:** Invariants validated dynamically in `tests/` (407 tests) and `scripts/verify.sh`.
- **Governed Worktree Lifecycle:** `dev` for active development, `stable` for release baseline, and clean temporary worktree conventions.

For detailed runtime acceptance evidence, matrix, and boundaries, see [RC3_RUNTIME_ACCEPTANCE.md](RC3_RUNTIME_ACCEPTANCE.md).
