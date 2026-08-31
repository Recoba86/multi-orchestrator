# Project State & Roadmap

## Current State: Develop Auto Team Policy Reconciliation — Local Checks Only

- **Checkpoint Date:** 2026-08-31
- **Baseline Commit:** `f043e51` (407-test weighted-routing baseline)
- **Prior Accepted Tags:** `rc3-runtime-accepted-2026-08-20`, `rc4-stable-promoted-2026-08-25`
- **Architecture Status:** DEVELOP reconciliation validated locally; live Host acceptance remains unclaimed
- **Runtime Status:** 418 local tests PASS, clean-room lifecycle and repo/runtime SHA parity PASS

### Key Architecture Deliverables
- **Dedicated Boss Architecture:** Completed and verified (Grok 4.6 High / Sol 5.6).
- **Root Controller & Dedicated Boss Plane Separation:** Strict protocol boundary with `fork_turns="none"`.
- **Implementer-Aware Independent Verification:** Non-self, model-family independent verification.
- **Canonical Auto Team Runtime Policy:**
  - One operator-selected model/effort policy is represented in `config/models.yaml` and translated exactly to runtime endpoints in `config/runtime-routing.yaml`.
  - SolMode / GrokMode remain explicit compatibility and observability state; they do not select alternate model chains.
  - Ordered primary-first failover routing replicates a healthy primary across parallel roles.
  - Master activation switch with instant legacy rollback kill-switch (`orchestrator-routing`).
  - Failure-domain health cooldown tracking with auto-expiry.
  - Append-only routing telemetry and target-share report generation.
- **Mission Trace:** Integrated via `~/.codex/orchestrator-traces/<mission_id>.json` and CLI reader `mission-trace`.
- **Dynamic Verification:** Invariants validated dynamically in `tests/` (418 tests) and `scripts/verify.sh`.
- **Live Acceptance:** **BLOCKED** for this reconciliation; no external-provider result is fabricated.
- **Governed Worktree Lifecycle:** `dev` for active development, `stable` for release baseline, and clean temporary worktree conventions.

For detailed runtime acceptance evidence, matrix, and boundaries, see [RC3_RUNTIME_ACCEPTANCE.md](RC3_RUNTIME_ACCEPTANCE.md).
