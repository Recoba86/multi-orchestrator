# Orchestrator V2 — Model Registry & Routing Policy

## 1. Provider-Qualified Endpoint Registry

| Endpoint ID | Capacity Domain | Transport Domain | Model | Accepted Efforts | Effective Effort Status | Notes |
|---|---|---|---|---|---|---|
| `PLUS_LUNA` | `openai_plus_capacity` | `openai_native` | `gpt-5.6-luna` | `[low, medium, high, max]` | `PROVEN` | Standard Worker Primary |
| `GEMINI_FLASH_HIGH` | `google_ag_capacity` | `nine_router_transport` | `nine-router/ag/gemini-3.7-flash-high` | `[low, high, max]` | `ACCEPTED_BUT_EFFECTIVE_UNKNOWN` | Scout Primary & Verifier |
| `DEEPSEEK_FLASH` | `opencode_go_capacity` | `nine_router_transport` | `opencode-go/deepseek-v4-flash` | `[low, high, max]` | `ACCEPTED_BUT_EFFECTIVE_UNKNOWN` | Scout / Worker Fallback |
| `DEEPSEEK_PRO` | `opencode_go_capacity` | `nine_router_transport` | `opencode-go/deepseek-v4-pro` | `[high, max]` | `ACCEPTED_BUT_EFFECTIVE_UNKNOWN` | Deep Worker Primary & Verifier |
| `OCG_LUNA` | `opencode_go_capacity` | `opencode_go_responses` | `opencode-go-responses/gpt-5.6-luna` | `[high, max]` | `ACCEPTED_BUT_EFFECTIVE_UNKNOWN` | Registry Fallback |
| `OPUS_4_6_THINKING` | `claude_opus_ag_capacity` | `nine_router_transport` | `nine-router/ag/claude-opus-4-6-thinking` | `[low, high, max]` | `ACCEPTED_BUT_EFFECTIVE_UNKNOWN` | Premium Reviewer (Read-Only) |
| `GROK_4_6_HIGH` | `xai_gcli_capacity` | `nine_router_transport` | `nine-router/gcli/grok-4.6-high` | `[high, max]` | `ACCEPTED_BUT_EFFECTIVE_UNKNOWN` | Grok Boss Profile |

---

## 2. Canonical Option A Routing (Deterministic 3-Attempt Chains)

### A. SCOUT (Read-Only Exploration)
1. **Attempt 1:** `GEMINI_FLASH_HIGH` (effort: `high`)
2. **Attempt 2:** `DEEPSEEK_FLASH` (effort: `high`)
3. **Attempt 3:** `PLUS_LUNA` (effort: `medium`)

### B. STANDARD_WORKER (Routine Implementation)
1. **Attempt 1:** `PLUS_LUNA` (effort: `high`)
2. **Attempt 2:** `GEMINI_FLASH_HIGH` (effort: `high`)
3. **Attempt 3:** `DEEPSEEK_FLASH` (effort: `high`)

### C. DEEP_WORKER (Complex / Algorithmic Depth)
1. **Attempt 1:** `DEEPSEEK_PRO` (effort: `max`)
2. **Attempt 2:** `PLUS_LUNA` (effort: `max`)
3. **Attempt 3:** `GEMINI_FLASH_HIGH` (effort: `max`)

### D. Base Verifier Pool & Filtering
Base Pool: `[GEMINI_FLASH_HIGH (high), DEEPSEEK_PRO (high), PLUS_LUNA (high)]`
- Implementers are strictly skipped (`SKIPPED_IMPLEMENTER_CONFLICT`).
- Next eligible non-conflicted candidate is dispatched with `fork_turns="none"`.
