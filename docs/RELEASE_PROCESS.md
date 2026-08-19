# Multi Orchestrator — Promotion & Release Process

## 1. Overview
In Multi Orchestrator, "release" refers to the rigorous promotion of an approved, verified development candidate from the `dev/` workspace (`develop` branch) into the `stable/` workspace (`main` branch), followed by explicit deployment to the local active Codex runtime (`~/.agents` and `~/.codex`).

```text
DEV SOURCE (develop)
       │
       ▼
Implementation & Unit Checks
       │
       ▼
Implementer-Independent Verification
       │
       ▼
Clean-Room Validation (scripts/install.sh & scripts/verify.sh)
       │
       ▼
Candidate Approved
       │
       ▼ (Explicit Merge / Promotion)
STABLE SOURCE (main)
       │
       ▼ (Explicit Execution of scripts/install.sh)
ACTIVE RUNTIME (~/.agents & ~/.codex)
```

---

## 2. Promotion Preconditions
Before promoting any candidate from `develop` to `main`:
1. **Clean Worktree:** `dev/` must have a completely clean Git working tree.
2. **Verification Passed:** All static verifier checks (`./scripts/verify.sh`) must pass with zero failures.
3. **Independent Audit Complete:** Verification must be conducted independently of the implementer.
4. **Zero Blockers:** No open P0 or P1 safety blocker or unresolved ambiguous write state may exist.
5. **Documentation Synchronized:** All affected documents (`README.md`, `docs/*.md`, `CHANGELOG.md`) must reflect the candidate behavior.

---

## 3. Promotion Procedure (develop -> main)
Promotion is performed explicitly between worktrees without dirtying worktree states:

```bash
# 1. Enter the stable worktree
cd /Users/amin/Documents/Witamin-Game/multi-orchestrator/stable

# 2. Confirm branch is main and working tree is clean
git status
git branch --show-current  # Must be 'main'

# 3. Merge approved develop candidate (fast-forward preferred)
git merge --ff-only develop

# 4. Push updated stable baseline to remote
git push origin main
```

---

## 4. Runtime Deployment Procedure
Deploying to the active Codex runtime is an explicit post-promotion step:

```bash
# 1. From the stable worktree, execute the installer
cd /Users/amin/Documents/Witamin-Game/multi-orchestrator/stable
./scripts/install.sh

# 2. Run the verifier against the active runtime
./scripts/verify.sh
```

**Prohibition:** Never run `./scripts/install.sh` directly from `dev/` to active runtime. Only tested Stable code from `stable/` may be deployed.

---

## 5. Rollback Strategy
If an unexpected issue arises post-deployment:
1. **Identify Last Known-Good Stable Commit:** Inspect Git history on `main` (`git log --oneline -n 5`).
2. **Revert / Checkout Stable Baseline:** Check out the previous stable commit in `stable/`.
3. **Execute Safe Uninstaller / Reinstaller:**
   ```bash
   ./scripts/uninstall.sh
   ./scripts/install.sh
   ```
4. **Verify Active Runtime:** Run `./scripts/verify.sh` to confirm safe baseline recovery.
