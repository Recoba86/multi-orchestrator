# Sol-Luna Orchestrator V2 (Release Candidate 3 — Dedicated Boss)

## Architecture

- **Skill Invocation:** `sol-luna-orchestrator-v2`
- **Control Plane:** Root Controller (active session model) validates execution and logs Mission Trace.
- **Decision Plane:** Dedicated Sol Boss (`gpt-5.6-sol`, High effort) dynamically spawned and maintained via child follow-up tasks.
- **Shared Policy Core:** `~/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md` (RC3 Architecture)
- **Topology:** Strict Hub-and-Spoke (`TOPOLOGY_HUB_AND_SPOKE_ONLY`). Subagents cannot spawn children or delegate.
- **Trace Persistence:** `~/.codex/orchestrator-traces/<mission_id>.json`

## Role Chains (Option A — Quality-First)

1. **SCOUT (Read-Only):** `GEMINI_FLASH_HIGH` (high) → `DEEPSEEK_FLASH` (high) → `PLUS_LUNA` (medium)
2. **STANDARD_WORKER (Write-Capable):** `GEMINI_FLASH_HIGH` (high) → `PLUS_LUNA` (max) → `DEEPSEEK_FLASH` (high)
3. **DEEP_WORKER (Write-Capable):** `DEEPSEEK_PRO` (max) → `PLUS_LUNA` (max) → `GEMINI_FLASH_HIGH` (max)
4. **VERIFIER (Read-Only):** Implementer-aware selection from `{ GEMINI_FLASH_HIGH (high), PLUS_LUNA (max), OCG_LUNA (high), DEEPSEEK_PRO (high) }` ensuring `verifier != implementer` and model-family independence.
5. **PREMIUM_SECOND_OPINION:** `OPUS_4_6_THINKING` (high) reserved exclusively for critical security, release-critical, or high-risk second opinions (Strictly Read-Only).

## Usage

```bash
codex
```

```text
Use $sol-luna-orchestrator-v2 to plan and execute this feature with multi-role subagents.
```
