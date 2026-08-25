# Multi Orchestrator — Self-Development Safety Guide

## 1. Fundamental Principle
Multi Orchestrator can be used to orchestrate enhancements, refactors, and feature additions to Multi Orchestrator itself.

**Critical Invariant (`NO_SELF_REPLACEMENT_DURING_ORCHESTRATION`):**
The running Active Stable orchestrator must NEVER modify, re-deploy, or overwrite its own active runtime (`~/.agents`, `~/.codex`) mid-mission.

---

## 2. Self-Development Operational Model

```text
ACTIVE STABLE RUNTIME (~/.agents, ~/.codex)
       │
       │ (Orchestrates the mission via Sol High / Grok Boss)
       ▼
DEV SOURCE WORKTREE (/.../multi-orchestrator/dev)
       │
       │ (Subagents edit code only within dev/)
       ▼
TESTED CANDIDATE
       │
       │ (Clean-room testing & independent audit in isolated temp HOME)
       ▼
MISSION COMPLETE & APPROVED
       │
       ▼ (Stage 1: Post-Mission Promotion to main in stable/)
PROMOTED STABLE SOURCE (/.../multi-orchestrator/stable)
       │
       ▼ (Stage 2: Explicit Deployment via installer)
NEW ACTIVE RUNTIME
```

---

## 3. Mandatory Safety Rules for Self-Development

1. **Active Parent Isolation:** The active Parent Boss (`gpt-5.6-sol` / `grok-4.6-high`) reads its normative policy from the currently deployed `~/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md`. It must NOT point its own runtime configuration to `dev/`.
2. **Worker Scope Restriction:** Subagents delegated to write code must receive `owned_files` rooted strictly in `/Users/example/multi-orchestrator/dev/...`. Under no circumstances may a worker own files in `~/.agents`, `~/.codex`, or `stable/`.
3. **Isolated Clean-Room Testing:** When validating installers or runtime changes, subagents MUST use an isolated temporary directory:
   ```bash
   TMP_HOME="$(mktemp -d)"
   ./scripts/install.sh --target-home "$TMP_HOME"
   ./scripts/verify.sh --target-home "$TMP_HOME"
   ./scripts/uninstall.sh --target-home "$TMP_HOME"
   rm -rf "$TMP_HOME"
   ```
   Subagents must never run install scripts against the live home directory.
4. **Independent Verification:** The candidate code in `dev/` must be verified by an independent verification agent (`fork_turns="none"`) before being returned to the parent Boss.
5. **Two-Stage Promotion:** Promotion to `main` and subsequent re-installation to `~/.agents` and `~/.codex` occur strictly as a post-mission step after the orchestration run has concluded successfully.

---

## 4. Concrete Example: Adding a Routing Feature to Multi Orchestrator

1. **Boss establishes plan:** Target is `/Users/example/multi-orchestrator/dev`.
2. **Worker 1 (Scout):** Inspects `dev/core/ORCHESTRATOR_CORE.md` and `dev/docs/MODELS.md`.
3. **Worker 2 (Standard Worker):** Modifies `dev/core/ORCHESTRATOR_CORE.md` (owned file: `/Users/example/multi-orchestrator/dev/core/ORCHESTRATOR_CORE.md`).
4. **Worker 3 (Independent Verifier):** Runs clean-room validation with `--target-home "$TMP_HOME"`. Verifies all invariants pass.
5. **Boss completes mission:** Commits changes to branch `develop` in `dev/`.
6. **Promotion & Deploy (Separate Steps):**
   - Stage 1: Merge `develop` into `main` in `stable/`.
   - Stage 2: Run `./scripts/install.sh` from `stable/` to update active runtime.
