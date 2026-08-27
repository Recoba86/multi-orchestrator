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

## Mode-Aware Runtime Routing & Operator Commands

Operators can manage runtime routing, persistent modes, and emergency rollback using:

```bash
# See complete routing status, switch state, and active config
orchestrator-routing status

# Enable runtime mode-aware routing
orchestrator-routing on

# Emergency Soft Rollback: immediately restore legacy wrapper authority
orchestrator-routing off

# Convenience: set mode AND enable runtime routing
orchestrator-routing use SolMode
orchestrator-routing use GrokMode

# Set persistent mode (without toggling master switch)
orchestrator-routing mode SolMode
orchestrator-routing mode GrokMode

# Inspect declarative model catalog and validate configuration
orchestrator-routing models
orchestrator-routing validate
orchestrator-routing report
```

Trigger phrases:
- "Use SolMode to plan and execute this feature with multi-role subagents."
- "Use GrokMode to plan and execute this feature with multi-role subagents."

When master routing is enabled (`orchestrator-routing on` / `use SolMode`), dynamic mode-aware routing and independent reviewer selection govern submitted requests. When disabled (`orchestrator-routing off`), exact legacy submitted-request authority is restored.

## Getting Help

The CLI itself is self-documenting:

```bash
orchestrator-routing
orchestrator-routing --help
orchestrator-routing <command> --help
orchestrator-routing help <command>
```
