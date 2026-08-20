# Project State & Roadmap

## Current State: Release Candidate 3 (RC3 — Dedicated Boss) — Checkpoint Accepted

- **Checkpoint Date:** 2026-08-20
- **Baseline Commit:** `131cc9393c6877976872fce052e9ed415b45f473`
- **Architecture Status:** ACCEPTED
- **Runtime Status:** READY_FOR_NORMAL_USE

### Key Architecture Deliverables
- **Dedicated Boss Architecture:** Completed and verified (Grok 4.6 High / Sol 5.6).
- **Root Controller & Dedicated Boss Plane Separation:** Strict protocol boundary with `fork_turns="none"`.
- **Implementer-Aware Independent Verification:** Non-self, model-family independent verification.
- **Mission Trace:** Integrated via `~/.codex/orchestrator-traces/<mission_id>.json` and CLI reader `mission-trace`.
- **Dynamic Verification:** Invariants validated dynamically in `tests/test_invariants.py` and `scripts/verify.sh`.
- **Governed Worktree Lifecycle:** `dev` for active development, `stable` for clean-room installation and deployment.

For detailed runtime acceptance evidence, matrix, and boundaries, see [RC3_RUNTIME_ACCEPTANCE.md](RC3_RUNTIME_ACCEPTANCE.md).
