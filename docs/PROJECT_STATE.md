# Multi Orchestrator — Operational Project State

## 1. Repository
- **Remote:** `https://github.com/Recoba86/multi-orchestrator.git`
- **Visibility:** `PRIVATE`
- **Default Branch:** `main`

---

## 2. Workspace & Worktrees
- **Project Source Root:** `/Users/amin/Documents/Witamin-Game/multi-orchestrator`
- **Stable Worktree:** `/Users/amin/Documents/Witamin-Game/multi-orchestrator/stable` (branch: `main`)
- **Dev Worktree:** `/Users/amin/Documents/Witamin-Game/multi-orchestrator/dev` (branch: `develop`)

---

## 3. Stable Source Reference vs. Active Runtime Baseline

### A. Current Stable Source
- **Authoritative Ref:** `main` / `origin/main`
- **Current SHA Discovery:**
  ```bash
  git rev-parse main
  # or
  git rev-parse origin/main
  ```

### B. Last Audited / Active Runtime Baseline (Before Governance Docs)
- **Commit SHA:** `8dd05b7c2fba9d7f8c25e37e8b52ca9027053969`
- *Note:* This represents the locked canonical baseline currently deployed in `~/.agents` and `~/.codex`. Future promotions to `main` advance the Stable source commit; runtime deployment is an explicit follow-up action.

---

## 4. Active Runtime State
- **Runtime Locations:** `~/.agents` and `~/.codex`
- **Current Deployment:** Tracks approved Stable (`main`), locked to canonical release v1.0.0.
- **Direct Dev Deployment:** Prohibited.

---

## 5. Authoritative Document Map
- **Agent Entrypoint & Preflight Guardrails:** [`AGENTS.md`](../AGENTS.md)
- **Normative Orchestration Policy & Schemas:** [`core/ORCHESTRATOR_CORE.md`](../core/ORCHESTRATOR_CORE.md)
- **Architecture Overview:** [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- **Safety Invariants & Failure Taxonomy:** [`docs/SAFETY.md`](SAFETY.md)
- **Model Registry & Routing Policy:** [`docs/MODELS.md`](MODELS.md)
- **Development Workflow Guide:** [`docs/DEVELOPMENT_WORKFLOW.md`](DEVELOPMENT_WORKFLOW.md)
- **Promotion & Release Process:** [`docs/RELEASE_PROCESS.md`](RELEASE_PROCESS.md)
- **Self-Development Safety Guide:** [`docs/SELF_DEVELOPMENT.md`](SELF_DEVELOPMENT.md)
