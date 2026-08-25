# Multi Orchestrator — Development Workflow Guide

## 1. Workspace & Worktree Architecture
The Multi Orchestrator source repository uses a permanent two-worktree layout under `/path/to/multi-orchestrator`:

```text
/path/to/multi-orchestrator/
├── stable/    (Checked out on branch: main)
└── dev/       (Checked out on branch: develop)
```

### Git Worktrees Explained
Both `stable/` and `dev/` share the exact same underlying Git database (`.git`), commit history, and remote tracking (`origin`), but provide separate physical working directories checked out to distinct branches:
- Changes made and committed in `dev/` exist on branch `develop`.
- `stable/` remains completely clean and locked on branch `main` at the latest approved release baseline.

---

## 2. Worktree Responsibilities

### Stable Worktree (`stable/` -> `main`)
- **Role:** The official, audited release baseline.
- **Allowed Operations:** Read-only inspection, release tagging, and explicit promotion merges from `develop`.
- **Forbidden Operations:** Routine code editing, experimental feature work, unverified fixes, direct worker write ownership.

### Dev Worktree (`dev/` -> `develop`)
- **Role:** The active development environment.
- **Allowed Operations:** Feature development, bug fixing, refactoring, routing experiments, verifier enhancements, and documentation authoring.

---

## 3. Standard Development Lifecycle

### Step 1: Preflight & Workspace Check
Always enter `dev/` and verify clean branch state:
```bash
cd /path/to/multi-orchestrator/dev
git status
git branch --show-current  # Must be 'develop' (or a feature branch)
```

### Step 2: Branching Strategy
- **Small / Documentation / Fixes:** Direct work on `develop` is permitted if changes are narrow and self-contained.
- **Larger Features / Complex Changes:** Create a dedicated branch from `develop`:
  ```bash
  git checkout -b feature/<feature-name> develop
  # or
  git checkout -b fix/<bug-name> develop
  ```

### Step 3: Implementation & Clean-Room Isolated Testing
Implement the changes within the assigned scope. When validating installers, skills, or verifier scripts, **always use an isolated temporary directory** to ensure the live environment (`~/.agents`, `~/.codex`) is never touched:

```bash
# Clean-Room Validation Pattern
TMP_HOME="$(mktemp -d)"

./scripts/install.sh --target-home "$TMP_HOME"
./scripts/verify.sh --target-home "$TMP_HOME"
./scripts/uninstall.sh --target-home "$TMP_HOME"

rm -rf "$TMP_HOME"
```

*Rule:* Never run `./scripts/install.sh` from `dev/` without `--target-home`. Plain `./scripts/verify.sh` tests your live environment, not the candidate!

### Step 4: Implementer-Independent Verification
Following the Multi Orchestrator core invariant, independent review and test execution must be performed by a verifier distinct from the implementer.

### Step 5: Merge back to `develop`
For feature branches, rebase or merge into `develop` once verified:
```bash
git checkout develop
git merge --ff-only feature/<feature-name>
git push origin develop
```

---

## 4. Worktree Hygiene & Safety Rules
- **No Blind Resets:** Never run `git reset --hard` or `git clean -fd` if unexpected changes exist. Inspect and report discrepancies.
- **No Force Pushes:** Do not force-push (`git push -f`) to `main` or `develop`.
- **Distinct Lifecycle States:**
  - `IMPLEMENTATION_COMPLETE`: Code is written and passes local isolated checks.
  - `VERIFICATION_COMPLETE`: Independent verifier has validated criteria with `PASS`.
  - `CANDIDATE_APPROVED`: All tests and safety invariants are satisfied.
  - `PROMOTED_TO_STABLE`: Merged into `main` in `stable/`.
  - `DEPLOYED_TO_RUNTIME`: Installed via `scripts/install.sh` from `stable/` into `~/.agents` and `~/.codex`.
