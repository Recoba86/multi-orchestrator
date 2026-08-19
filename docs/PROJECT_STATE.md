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

## 3. Current Stable Baseline
- **Stable Baseline Commit:** `8dd05b7c2fba9d7f8c25e37e8b52ca9027053969` (Initial Release Locked)
- *Note:* The commit hash above represents the current locked Stable release on `main`. Work occurring on `develop` does not advance Stable until explicit promotion.

---

## 4. Active Runtime State
- **Runtime Locations:** `~/.agents` and `~/.codex`
- **Deployed Baseline:** Tracks approved Stable (`main`), locked to canonical release v1.0.0.
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
