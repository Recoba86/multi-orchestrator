# Models and Provider Registry (RC3)

## Endpoint Registry

| Endpoint ID | Canonical Model String | Capacity Domain | Accepted Efforts | Policy Max |
|---|---|---|---|---|
| `SOL_HIGH` | `gpt-5.6-sol` | `openai_plus_capacity` | `[low, medium, high, xhigh, max, ultra]` | `high` (normative boss) |
| `GROK_4_6_HIGH` | `nine-router/gcli/grok-4.6-high` | `xai_gcli_capacity` | `[high, max]` | `high` (normative boss) |
| `PLUS_LUNA` | `gpt-5.6-luna` | `openai_plus_capacity` | `[low, medium, high, max]` | `max` |
| `GEMINI_FLASH_HIGH` | `nine-router/ag/gemini-3.7-flash-high` | `google_ag_capacity` | `[low, high, max]` | `high` |
| `DEEPSEEK_FLASH` | `opencode-go/deepseek-v4-flash` | `opencode_go_capacity` | `[low, high, max]` | `high` |
| `DEEPSEEK_PRO` | `opencode-go/deepseek-v4-pro` | `opencode_go_capacity` | `[high, max]` | `max` |
| `OCG_LUNA` | `opencode-go-responses/gpt-5.6-luna` | `opencode_go_capacity` | `[high, max]` | `high` |
| `OPUS_4_6_THINKING` | `nine-router/ag/claude-opus-4-6-thinking` | `claude_opus_ag_capacity` | `[low, high, max]` | `high` (Read-Only) |

## Role Chains

- **SCOUT:** `GEMINI_FLASH_HIGH` (high) → `DEEPSEEK_FLASH` (high) → `PLUS_LUNA` (medium)
- **STANDARD_WORKER:** `GEMINI_FLASH_HIGH` (high) → `PLUS_LUNA` (max) → `DEEPSEEK_FLASH` (high)
- **DEEP_WORKER:** `DEEPSEEK_PRO` (max) → `PLUS_LUNA` (max) → `GEMINI_FLASH_HIGH` (max)
- **VERIFIER:** Implementer-aware selection enforcing `verifier != implementer` and model family independence (`PLUS_LUNA` ↔ `OCG_LUNA` conflict).
- **PREMIUM_SECOND_OPINION:** `OPUS_4_6_THINKING` (Strictly Read-Only).
