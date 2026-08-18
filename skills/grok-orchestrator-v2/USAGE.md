# Grok Orchestrator V2 (INITIAL_RELEASE_RC2)

## Architecture

- **Boss:** `nine-router/gcli/grok-4.6-high` (High effort, Profile: `~/.codex/grok-v2.config.toml`)
- **Shared Policy Core:** `~/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md` (INITIAL_RELEASE_RC2)
- **Topology:** Strict Hub-and-Spoke (`TOPOLOGY_HUB_AND_SPOKE_ONLY`). Subagents cannot spawn children or delegate.
- **Execution Invariant:** Strictly sequential fallback per logical task (max 3 actual attempts) with explicit task packets (`WORKER_TASK_PACKET`, `VERIFICATION_PACKET`, `prior_attempt_summary`), `fork_turns="none"`, and implementer-aware independent verification.

## Role Chains (Option A — Quality-First)

1. **SCOUT (Read-Only):** `GEMINI_FLASH_HIGH` (high) → `DEEPSEEK_FLASH` (high) → `PLUS_LUNA` (medium)
2. **STANDARD_WORKER (Write-Capable):** `PLUS_LUNA` (high) → `GEMINI_FLASH_HIGH` (high) → `DEEPSEEK_FLASH` (high)
3. **DEEP_WORKER (Write-Capable):** `DEEPSEEK_PRO` (max) → `PLUS_LUNA` (max) → `GEMINI_FLASH_HIGH` (max)
4. **VERIFIER (Read-Only):** Implementer-aware selection from `{ GEMINI_FLASH_HIGH (high), DEEPSEEK_PRO (high), PLUS_LUNA (high) }` ensuring `verifier != implementer`.
5. **PREMIUM_SECOND_OPINION:** `OPUS_4_6_THINKING` (high) reserved exclusively for critical security, release-critical, or high-risk second opinions (Strictly Read-Only).

## Usage

```bash
codex --profile grok-v2
```

```text
Use $grok-orchestrator-v2 to plan and execute this feature with multi-role subagents.
```
