# Auto Team Usage Guide

Auto Team provides high-discipline software engineering orchestration using a 3-plane architecture:
- **Control Plane (Root Controller):** Validates protocols, manages workspace isolation, losslessly relays subagent communications, and records immutable Mission Traces with Model Telemetry.
- **Decision Plane (Dedicated Boss):** Formulates self-contained task packets, coordinates role assignments, evaluates verifier findings, and issues final decisions.
- **Execution Plane (Workers & Verifiers):** Bounded write workers and read-only adversarial verifiers adhering to strict cognitive independence.

---

Native allocation and effective child execution are `HOST_EXTERNAL`.
## 1. Skill Invocation

Invoke Auto Team using the canonical trigger:

```text
$autoteam: <your task or project goal>
```

Alternatively, invoke via standard prompt:
```text
Use autoteam to plan and implement <feature or bugfix>.
```

---

## 2. Model Roles & Routing Modes

Auto Team operates in two persistent operator-selected routing modes:
- **SolMode (Default):** Sol High (`gpt-5.6-sol`) is primary Boss; Grok High, Opus, and Gemini Flash provide multi-tier worker/verifier capacity.
- **GrokMode:** Grok 4.6 High (`nine-router/gcli/grok-4.6-high`) is primary Boss with zero GPT Plus throughput.

### Management Commands:
```bash
# Check current active mode and health status
orchestrator-mode status

# Switch to SolMode
orchestrator-mode set SolMode

# Switch to GrokMode
orchestrator-mode set GrokMode

# Enable master runtime routing
orchestrator-routing on

# Inspect model supply recommendations
doctor
```

Chat triggers: `Use SolMode` and `Use GrokMode` persist operator mode without automatic health-driven mode flips.

Role chains are ordered priority/failover. Parallel agents of the same role replicate the healthy primary. Fallbacks activate only for unavailability, provider failure, cooldown, or independence exclusion.

---

## 3. End-of-Run Observability & Telemetry

At the conclusion of each mission, Auto Team renders:
1. **Model Telemetry Table:** Breakdown of exact request, token, and cache efficiency by `Model` + `Role`.
2. **Routing Decisions Table:** Transparent record of candidate evaluations showing `SELECTED`, `SKIPPED`, and `FAILED` results with explicit reasons (`INDEPENDENT`, `SAME_FAMILY`, `FALLBACK`, `ESCALATION`).
