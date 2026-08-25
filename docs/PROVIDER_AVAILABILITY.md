# Model Availability and Provider Health (RC3)

This document describes the read-only, provider-agnostic model availability and provider health foundation.

## Core Architectural Boundaries

1. **State Separation**:
   - `Configured / Recommendation`: Declared in `config/models.yaml` (role preferred/fallback lists).
   - `Declared / Discovered`: Local TOML declarations in `.codex/*.config.toml` or `.codex/agents/*.toml`.
   - `Capability Metadata`: Built-in profiles or offline evidence-backed claims in `model-intelligence.yaml`.
   - `Model Availability`: Point-in-time reachability and operational status of a model (`AVAILABLE`, `UNAVAILABLE`, `UNKNOWN`).
   - `Provider Health`: Point-in-time reachability and health of an underlying provider (`HEALTHY`, `UNAVAILABLE`, `UNKNOWN`).

   Neither configuration, discovery, nor capability profiling proves that a model is `AVAILABLE` or that a provider is `HEALTHY`.

2. **No Provider Inference**:
   - Provider identity is explicit or `UNKNOWN`. Model identifier strings (e.g., prefixes like `openai/`, `nine-router/`, `opencode-go/`) are never parsed or mapped heuristically to inferred providers.

3. **Status Taxonomy & Freshness Taxonomy**:
   - Model states: `AVAILABLE`, `UNAVAILABLE`, `UNKNOWN`.
   - Provider states: `HEALTHY`, `UNAVAILABLE`, `UNKNOWN`.
   - Freshness states: `FRESH`, `STALE`, `UNKNOWN`.
   - Error categories: `AUTH`, `RATE_LIMIT`, `QUOTA`, `SERVER`, `TIMEOUT`, `NOT_FOUND`, `MALFORMED_RESPONSE`, `PROBE_UNSUPPORTED`, `UNKNOWN`.
   - Probe failure markers: `PROBE_UNSUPPORTED`, `PROBE_FAILED`.
   - No separate health cache distinction exists; runtime health is descriptive point-in-time state.

4. **Provenance & Measured Data Invariants**:
   - `checked_at` (timezone-aware UTC datetime; aware timestamps with positive/negative offsets are normalized to `timezone.utc`) and `latency_ms` (finite non-negative float) are recorded only when an actual probe is executed.
   - An active probe resulting in `AVAILABLE` or `HEALTHY` strictly requires `FRESH` freshness, timezone-aware `checked_at`, and finite non-negative `latency_ms`.
   - Offline observations and `PROBE_UNSUPPORTED` records set `UNKNOWN` status and `UNKNOWN` freshness with no timestamps or latency measurements (`None`).

5. **Security & Zero Network Operations**:
   - Default mode operates strictly offline: zero network requests, zero subprocess execution, zero credential reads.
   - When active probes are requested (`--active-probes`), because no supported adapter exists, the foundation immediately reports `UNKNOWN` with `PROBE_UNSUPPORTED` without executing network calls or launching background threads/processes.
   - Identifiers and details are sanitized and deterministically bounded against control-character, escape sequence (ANSI), and newline injection. Identifiers are backslash-escaped (backslashes render escaped as valid content) and bounded at <=384 display characters with a stable truncation marker (`...`).

6. **Resolver Readiness & Non-Selecting Advisory Role**:
   - This layer is strictly descriptive and advisory. It performs no model selection, routing, allocation, or execution.

## Probe-Source Matrix

| Source / Scope | Source Type | Side Effects | Support Level | Reported State | Provenance |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `config/models.yaml` | Static config | None (read-only file parse) | Supported | Role preferred/fallback lists | `configured` |
| Local Codex TOML (`.codex/*.toml`) | Local filesystem | None (read-only declaration parse) | Supported | Discovered model strings | `codex-profiles` / `codex-agents` |
| Built-in capabilities | In-memory registry | None (pure lookup) | Supported | Advisory capability tags | `builtin-profile` |
| Intelligence cache (`model-intelligence.yaml`) | Local offline cache | None (read-only YAML parse) | Supported | Advisory score/confidence claims | `fixture` / offline evidence |
| Provider APIs (Remote HTTP endpoints) | Network / Remote API | Prohibited (zero network) | Unsupported | `UNKNOWN` (`PROBE_UNSUPPORTED`) | `probe-unsupported` |
| Host / router runtime | Subprocess / IPC | Prohibited (zero execution) | Unsupported | `UNKNOWN` (`PROBE_UNSUPPORTED`) | `probe-unsupported` |
| Active probe adapters (Injected test seam) | Pure callable seam | In-memory test mock only | Supported in test | Invariant-validated record | `active-probe` |

## Live Validation & Verification Table

| Validation State | Condition / Meaning | Authority & Route Evidence |
| :--- | :--- | :--- |
| **PROVEN** | Point-in-time reachability confirmed via explicit active probe adapter with verified `FRESH` freshness, timezone-aware timestamp, and measured non-negative latency. | Requires explicit provider binding and verified execution response. Never inferred from configuration or capability hints. |
| **UNAVAILABLE** | Probe returned an explicit failure category (e.g. `AUTH`, `RATE_LIMIT`, `SERVER`, `TIMEOUT`) or provider confirmed unreachable. | Grounded in point-in-time probe failure without fabricated error metadata. |
| **UNPROVEN** | Default offline observation or unsupported probe (`UNKNOWN` status, `UNKNOWN` freshness). No live verification performed. | Static declarations, missing adapters, or default Doctor runs without active probe support. |
