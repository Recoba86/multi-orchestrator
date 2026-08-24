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
- **Purpose:** Known-good, audited, approved Multi Orchestrator source baseline.
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
  - Do NOT deploy `develop` directly to active runtime. Never run `./scripts/install.sh` from `dev/` without `--target-home`.
  - Do NOT symlink runtime files to the `dev/` worktree.
  - Runtime deployment is an explicit post-promotion step originating ONLY from approved Stable (`main`).

---

## 5. Candidate Validation & Development Workflow
```text
dev/ (develop)
   │
   ├─► Feature / Fix Implementation
   ├─► Clean-Room Isolated Validation (TMP_HOME="$(mktemp -d)")
   │      ./scripts/install.sh --target-home "$TMP_HOME"
   │      ./scripts/verify.sh --target-home "$TMP_HOME"
   │      ./scripts/uninstall.sh --target-home "$TMP_HOME"
   │      rm -rf "$TMP_HOME"
   │
   ├─► Implementer-Independent Verification (`verifier != implementer`)
   ▼
Approved Candidate
   │
   ▼ (Stage 1: Explicit Promotion / Merge to main)
stable/ (main)
   │
   ▼ (Stage 2: Explicit Deployment via scripts/install.sh)
Active Runtime (~/.agents, ~/.codex)
```

### Critical Separation: Dev is Not Stable
- **Implementation complete** does NOT authorize promotion.
- **Verification complete** does NOT automatically authorize deployment.
- Promotion to `main` is an explicit action.
- Deployment to runtime is a second, separate explicit action.

---

## 6. Self-Development Safety Rules
When Multi Orchestrator is used to develop or enhance Multi Orchestrator itself:
1. **The running Active Stable orchestrator controls the mission.**
2. **Worker assignments MUST target `dev/` or a feature worktree only.**
3. **The running orchestrator MUST NOT mutate its own active runtime (`~/.agents`, `~/.codex`) mid-mission.**
4. **Candidate verification occurs in isolated temporary HOME directories (`--target-home`).**
5. **Independent verification audits Dev candidate artifacts before promotion.**
6. **Only after mission completion and promotion to `main` may the new version be deployed to active runtime.**

---

## 7. Core Architecture & Safety Invariants
Multi Orchestrator is governed by strict, fail-closed safety contracts:
- **Strict Hub-and-Spoke (`TOPOLOGY_HUB_AND_SPOKE_ONLY`):** The Boss coordinates; Controller-submitted packets assign subagents as leaf nodes, and the Controller refuses packets requesting child spawning, peer delegation, or nested chains. Parent prompt instructions cannot override this rule.
- **Requested Context Isolation (`fork_turns="none"`):** Controller-submitted packets request zero inherited parent history; all required context is passed via self-contained packets (`WORKER_TASK_PACKET`, `VERIFICATION_PACKET`, `prior_attempt_summary`). Host context construction remains `HOST_EXTERNAL`.
- **Packet Invalidity Pre-Dispatch Check (`PACKET_INVALID`):** The Controller MUST NOT submit invalid or incomplete task packets or provider fallback requests. Packet construction/validation failure is a parent contract defect, not a provider failure.
- **Independent Verification (`IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK`):** The Controller rejects packets assigning an implementer as its own verifier. Verifier chain exhaustion leaves tasks `INCOMPLETE` without self-verification.
- **Fail-Closed Mutation Safety:** The Controller refuses secondary write requests after ambiguous execution states (`AMBIGUOUS_EXECUTION_STATE`).
- **Dedicated Read-Only Reviewer:** The Controller's premium-review packet specifies Claude Opus 4.6 Thinking as `READ_ONLY` (`write_ownership: NONE`); Host enforcement remains `HOST_EXTERNAL`.

### Authoritative Reference Documents
- **Normative Orchestration Policy & Schemas:** [`core/ORCHESTRATOR_CORE.md`](core/ORCHESTRATOR_CORE.md)
- **Architecture Overview:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Safety Invariants & Failure Taxonomy:** [`docs/SAFETY.md`](docs/SAFETY.md)
- **Model Registry & Routing Policy:** [`docs/MODELS.md`](docs/MODELS.md)
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
