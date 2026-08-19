# Project State & Roadmap

## Current State: Release Candidate 3 (RC3 — Dedicated Boss)

- **Dedicated Boss Architecture:** Completed and verified.
- **Root Controller & Dedicated Boss Plane Separation:** Implemented.
- **Mission Trace:** Integrated via `~/.codex/orchestrator-traces/<mission_id>.json` and CLI reader `mission-trace`.
- **Dynamic Verification:** Invariants validated dynamically in `scripts/verify.sh` and `tests/test_invariants.py`.
- **Governed Worktree Lifecycle:** `dev` for active development, `stable` for clean-room installation and deployment.
