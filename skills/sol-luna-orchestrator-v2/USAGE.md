# Sol-Luna Orchestrator V2 (Release Candidate 3 — Dedicated Boss)

## Architecture

- **Skill Invocation:** `sol-luna-orchestrator-v2`
- **Control Plane:** Root Controller validates protocol and submits native child requests to the external Host, then logs observable Mission Trace evidence.
- **Decision Plane:** Dedicated Sol Boss request (`gpt-5.6-sol`, High effort), maintained using the Host-returned child identity and follow-up tasks.
- **Shared Policy Core:** `~/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md` (RC3 Architecture)
- **Declarative Role Config:** [`config/models.yaml`](../../config/models.yaml) (and installed `~/.agents/config/models.yaml`) documents optional, ordered recommendations for `planner`, `scout`, `worker`, and `reviewer`. Read-only Doctor evaluates declarations, capabilities, and deterministic advisory resolution. Unresolved config never auto-substitutes models; user modifies config explicitly via `configure-models`.
- **Topology:** Strict Hub-and-Spoke repository protocol (`TOPOLOGY_HUB_AND_SPOKE_ONLY`); this is not Host-wide native enforcement.
- **Trace Persistence:** `~/.codex/orchestrator-traces/<mission_id>.json`
- **Execution Boundary:** Native allocation and effective identity are `HOST_EXTERNAL`; see Core's authoritative Execution Boundary Model. `PreToolUse Agent` is optional, not a strict Host boundary.

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

## Mode-Aware Routing (Shadow Posture)

Operators can manage persistent routing modes using:

```bash
orchestrator_mode.py status
orchestrator_mode.py SolMode
orchestrator_mode.py GrokMode
```

Trigger phrases:
- "Use SolMode to plan and execute this feature with multi-role subagents."
- "Use GrokMode to plan and execute this feature with multi-role subagents."

During shadow posture, submitted requests continue to use legacy wrapper bindings until explicit activation in Task 12.
