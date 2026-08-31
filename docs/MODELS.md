# Models and Provider Registry (RC3)

The registry defines request-contract constraints. The Controller validates requested endpoint, model, effort, role, and access before Host submission; native Host dispatch, allocation, and final effective identity remain `HOST_EXTERNAL`.

## Declarative operator policy and logical-role views

[`config/models.yaml`](../config/models.yaml) provides a separate,
provider-agnostic operator policy. Its `operator_policy` section is the
canonical ordered model/effort chain for `BOSS`, `SCOUT`, `STANDARD_WORKER`,
`DEEP_WORKER`, `VERIFIER`, and `PREMIUM_SECOND_OPINION`. The four logical roles
(`planner`, `scout`, `worker`, and `reviewer`) are advisory views whose
`preferred` plus `fallback` lists project the corresponding canonical chains.

The current flow is user-owned `models.yaml` → read-only Doctor structural
validation → local Codex declaration discovery and exact-string comparison.
Centralized policy semantics (`core/model_policy.py`) and deterministic offline
advisory resolution (`core/model_resolver.py`) evaluate configured preferences
against local declarations, offline availability observations, capability
compatibility, and intelligence profiles. Doctor reports these structured
resolution outcomes alongside discovery and capability analysis. Model
preferences can be safely updated via `configure-models`. This resolution is
purely offline and advisory: it never probes remote providers, mutates
configuration automatically, or overrides normative Core routing. The schema
and strict unknown-field behavior are covered by
[`tests/test_model_configuration.py`](../tests/test_model_configuration.py).

The endpoint chains below are the deterministic runtime translation of that
operator policy. Provider/model strings are not claims of universal
availability or runtime allocation.

## Model intelligence foundation (offline and advisory)

Model Intelligence is a local, descriptive cache. It provides advisory evidence
inputs for the offline resolver, but does not probe providers or change a request. The cache loader requires
`schema_version: 1` and top-level `evidence` and `models` lists. Evidence
entries carry `id`, `source_type`, `strength`, `locator`, `observed_at`, and
`summary` (with optional `expires_at`). Model entries carry an exact `identity`
and `claims`; each claim carries `capability`, an integer `score` from `0` to
`10`, a `confidence` category, and non-empty `evidence_ids` referring to the
cache evidence registry. Missing or malformed required fields, duplicate
evidence IDs, dangling evidence IDs, duplicate exact identities, invalid
timestamps, or a version other than `1` make the cache invalid.

The fixed capability dimensions consumed by current advisory role ranking are
`reasoning`, `coding`, `analysis`, `fast`, `long_context`, `review`, and
`cost_effective`. Additional imported capability labels may remain stored in
the cache, but they do not affect ranking unless they are present in a role
weight map. Evidence strength and claim confidence are separate `LOW`,
`MEDIUM`, and `HIGH` categories. Confidence contributes fixed advisory values
`0.25`, `0.50`, and `0.90`; these values are arithmetic weights, not calibrated
probabilities.
`observed_at` and evaluation `as_of` timestamps must include a timezone;
`expires_at`, when present, also carries a timezone. A profile is `ACTIVE`,
`STALE`, `CONFLICTED`, or `UNKNOWN`: expired evidence is stale, future or
missing evidence is unknown, and disagreeing claims for one capability are
conflicted. Conflicting values are withheld; they are never averaged.

Identity handling is exact. The raw `identity` string is authoritative for
matching and joins. A derived display key applies Unicode NFKC normalization
and `strip()` only; it is presentation metadata, not alias inference. Distinct
raw strings remain distinct even when their display keys collide.

Recommendations are advisory only and consider `ACTIVE` profiles that Doctor
has matched to a discovered raw identity. Each role uses fixed weights:

| Role | Fixed capability weights |
|---|---|
| `planner` | `reasoning .40`, `analysis .25`, `long_context .20`, `coding .15` |
| `scout` | `fast .40`, `analysis .30`, `cost_effective .20`, `reasoning .10` |
| `worker` | `coding .40`, `reasoning .30`, `fast .20`, `long_context .10` |
| `reviewer` | `review .40`, `analysis .30`, `reasoning .20`, `long_context .10` |

The fixed coverage gate is `>= 50%` of a role's total weight. Ranking sorts by
weighted score descending, then coverage descending, then mapped confidence
descending, then exact raw identity ascending. This order is deterministic and
does not select, route, allocate, or authorize a model; cache-only profiles are
excluded by Doctor.

`EXTERNAL_RESEARCH_BOUNDARY: no supported programmatic web-search/external HTTP API exists.`
Reviewed external research may be transcribed into inert YAML with explicit
provenance and timestamps, but this project performs no browsing, fetching,
execution, or model self-evaluation. See
[`MODEL_CONFIGURATION.md`](MODEL_CONFIGURATION.md) for the cache example,
configuration mutation rules, and security gates.

## Endpoint Registry

| Endpoint ID | Canonical Model String | Capacity Domain | Accepted Efforts | Policy Max / Binding |
|---|---|---|---|---|
| `SOL_HIGH` | `gpt-5.6-sol` | `gpt_plus` | `[high]` | BOSS / DEEP_WORKER / VERIFIER |
| `GROK_4_6_HIGH` | `nine-router/gcli/grok-4.6-high` | `supergrok` | `[high]` | BOSS / DEEP_WORKER / VERIFIER |
| `GROK_CURSOR_HIGH` | `nine-router/cu/cursor-grok-4.6-high` | `supergrok` | `[high]` | BOSS fallback |
| `GEMINI_FLASH_MEDIUM` | `nine-router/ag/gemini-3.7-flash-medium` | `gemini` | `[medium]` | SCOUT |
| `GEMINI_FLASH_HIGH` | `nine-router/ag/gemini-3.7-flash-high` | `gemini` | `[high]` | STANDARD_WORKER / DEEP_WORKER / VERIFIER |
| `QWEN_3_8_FLASH` | `commandcode/qwen3.8-flash` | `cheap` | `[high]` | SCOUT fallback |
| `PLUS_LUNA` | `gpt-5.6-luna` | `gpt_plus` | `[max]` | STANDARD_WORKER fallback |
| `OPUS_COMBO` | `nine-router/Opus` | `opus` | `[high]` | VERIFIER / PREMIUM_SECOND_OPINION; read-only |
| `PLUS_TERRA` | `gpt-5.6-terra` | `gpt_plus` | `[high]` | PREMIUM_SECOND_OPINION fallback |

Legacy catalog entries remain available only for rollback and validation
fixtures. Their presence does not add candidates to the canonical chains.

## Canonical Auto Team Role Chains

- **BOSS / Planner:** `SOL_HIGH` (`gpt-5.6-sol`, high) → `GROK_4_6_HIGH` (`nine-router/gcli/grok-4.6-high`, high) → `GROK_CURSOR_HIGH` (`nine-router/cu/cursor-grok-4.6-high`, high)
- **SCOUT:** `GEMINI_FLASH_MEDIUM` (`nine-router/ag/gemini-3.7-flash-medium`, medium) → `QWEN_3_8_FLASH` (`commandcode/qwen3.8-flash`, high)
- **STANDARD_WORKER:** `GEMINI_FLASH_HIGH` (`nine-router/ag/gemini-3.7-flash-high`, high) → `PLUS_LUNA` (`gpt-5.6-luna`, max)
- **DEEP_WORKER:** `GROK_4_6_HIGH` (high) → `GEMINI_FLASH_HIGH` (high) → `SOL_HIGH` (high)
- **VERIFIER:** `SOL_HIGH` (high) → `GROK_4_6_HIGH` (high) → `OPUS_COMBO` (`nine-router/Opus`, high) → `GEMINI_FLASH_HIGH` (high), after implementer-family exclusion
- **PREMIUM_SECOND_OPINION:** `OPUS_COMBO` (high) → `PLUS_TERRA` (`gpt-5.6-terra`, high), read-only

SolMode and GrokMode are persistent operator state for compatibility, status,
and telemetry. Both modes use these same canonical chains; mode does not
silently exclude GPT Plus candidates or create alternate model policy.
