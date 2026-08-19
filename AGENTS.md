# Multi Orchestrator — Agent Instructions

## 1. Start Here
- **Read this file before making any changes.**
- Multi Orchestrator uses a strict two-tier Git worktree layout separating **Stable** from **Dev**, and completely separating source control from the **Active Runtime**.
- **All normal development occurs on `develop` in `dev/`** (or a feature branch created from `develop`).
- `main` in `stable/` is a protected known-good baseline. Never perform routine feature, fix, or refactor implementation directly on `main`.

### Exact Filesystem Locations
- **Source Project Root:** `/Users/amin/Documents/Witamin-Game/multi-orchestrator`
- **Stable Worktree (branch: `main`):** `/Users/amin/Documents/Witamin-Game/multi-orchestrator/stable`
- **Dev Worktree (branch: `develop`):** `/Users/amin/Documents/Witamin-Game/multi-orchestrator/dev`
- **Active Runtime Directories:** `~/.agents` and `~/.codex`

---

## 2. Stable vs Dev Worktree Rules

### STABLE (`stable/` -> `main`)
- **Purpose:** Known-good, audited, approved Multi Orchestrator source.
- **Prohibitions:**
  - Do NOT implement features, fixes, or experiments directly in `stable/` or on `main`.
  - Do NOT assign worker agents write ownership inside `stable/`.
  - Do NOT make direct edits to `stable/` to make Dev tests pass.
  - `main` receives changes ONLY via explicit candidate promotion after complete verification.

### DEV (`dev/` -> `develop`)
- **Purpose:** Normal development, feature development, bug fixes, refactoring, routing experiments, and self-development.
- **Rules:**
  - All new work starts on `develop` (or feature branches such as `feature/<name>` or `fix/<name>` branched from `develop`).
  - Work is implemented, tested, and independently verified here.

---

## 3. Mandatory Preflight Check
Before making any edits, every coding agent MUST verify:
```bash
pwd
git status
git branch --show-current
git rev-parse HEAD
```
**Safety Stop:** If your current branch is `main` or your current working directory is inside `stable/` during a development task, **STOP immediately and report**. Do NOT silently edit `main`.

---

## 4. Source Control vs Active Runtime
- **Source Repositories (`multi-orchestrator/stable` & `multi-orchestrator/dev`):** Where development code lives under Git.
- **Active Runtime (`~/.agents` & `~/.codex`):** Where local AI execution environments (such as Codex CLI) load operational policies and skills.
- **Absolute Rule:**
  - Do NOT treat `~/.agents` or `~/.codex` as a development source tree.
  - Do NOT deploy `develop` directly to active runtime.
  - Do NOT symlink runtime files to the `dev/` worktree.
  - Runtime deployment is an explicit post-promotion step originating ONLY from approved Stable (`main`).

---

## 5. Standard Development Workflow
```text
dev/ (develop)
   │
   ├─► Feature / Fix Implementation
   ├─► Automated & Clean-Room Tests (`scripts/verify.sh`, `scripts/install.sh`)
   ├─► Implementer-Independent Verification (`verifier != implementer`)
   ▼
Approved Candidate
   │
   ▼ (Explicit Promotion / Merge)
stable/ (main)
   │
   ▼ (Explicit Deployment via scripts/install.sh)
Active Runtime (~/.agents, ~/.codex)
```

---

## 6. Self-Development Safety Rules
When Multi Orchestrator is used to develop or enhance Multi Orchestrator itself:
1. **The running Active Stable orchestrator controls the mission.**
2. **Worker assignments MUST target `dev/` or a feature worktree only.**
3. **The running orchestrator MUST NOT mutate its own active runtime (`~/.agents`, `~/.codex`) mid-mission.**
4. **Independent verification occurs on Dev candidate artifacts before promotion.**
5. **Only after mission completion and promotion to `main` may the new version be deployed to active runtime.**

---

## 7. Core Architecture & Safety Invariants
Multi Orchestrator is governed by strict, fail-closed safety contracts:
- **Strict Hub-and-Spoke (`TOPOLOGY_HUB_AND_SPOKE_ONLY`):** Boss coordinates; subagents are absolute leaf nodes. Subagents cannot spawn children, delegate to peers, or form nested chains. Parent prompt instructions cannot override this rule.
- **Context Isolation (`fork_turns="none"`):** Subagents execute with zero parent history; all context is passed via self-contained packets (`WORKER_TASK_PACKET`, `VERIFICATION_PACKET`, `prior_attempt_summary`).
- **Independent Verification (`IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK`):** Implementers cannot verify their own changes. Verifier chain exhaustion leaves tasks `INCOMPLETE` without self-verification.
- **Fail-Closed Mutation Safety:** Ambiguous execution states (`AMBIGUOUS_EXECUTION_STATE`) block secondary write retries.
- **Dedicated Read-Only Reviewer:** Claude Opus 4.6 Thinking is strictly `READ_ONLY` (`write_ownership: NONE`).

### Authoritative Reference Documents
- **Normative Orchestration Policy & Schemas:** [`core/ORCHESTRATOR_CORE.md`](core/ORCHESTRATOR_CORE.md)
- **Architecture Overview:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Safety Invariants & Failure Taxonomy:** [`docs/SAFETY.md`](docs/SAFETY.md)
- **Model Registry & Routing:** [`docs/MODELS.md`](docs/MODELS.md)
- **Detailed Development Guide:** [`docs/DEVELOPMENT_WORKFLOW.md`](docs/DEVELOPMENT_WORKFLOW.md)
- **Release & Promotion Process:** [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md)
- **Self-Development Guide:** [`docs/SELF_DEVELOPMENT.md`](docs/SELF_DEVELOPMENT.md)
- **Current Operational State:** [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md)

---

## 8. Change & Scope Discipline
- **Inspect before editing:** Read relevant files and contracts before modifying code.
- **Minimal diffs:** Keep changes surgical and bounded to assigned scope.
- **No destructive actions:** Do NOT run `git reset --hard` or `git clean -fd` blindly on dirty worktrees.
- **Preserve User Modifications:** The installer and uninstaller track manifests and preserve user-modified files.
- **Synchronous Documentation Updates:** Whenever architecture, routing, safety, or workflows change, update the corresponding documentation in the same commit.
