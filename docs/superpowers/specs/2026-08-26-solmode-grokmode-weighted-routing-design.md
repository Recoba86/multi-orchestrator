# SolMode / GrokMode Weighted Runtime Routing — Design Specification

Status: APPROVED DESIGN (Phase 0)
Date: 2026-08-26
Repository: Recoba86/multi-orchestrator
Baseline: `5bf2e25da255e3e66628e8f040b73390bbdc0598` (develop == main == origin)
Branch: `feat/solmode-grokmode-weighted-routing`

---

## 1. Purpose and Scope

This specification defines a **mode-aware weighted runtime routing subsystem** for
Multi Orchestrator. It introduces two user-facing, manually selected, persistent
modes — **SolMode** and **GrokMode** — that govern deterministic weighted model
selection for the runtime roles (`SCOUT`, `STANDARD_WORKER`, `DEEP_WORKER`,
`VERIFIER`) while preserving every existing RC3 invariant:

- Dedicated Boss remains mandatory; Boss continuity survives mode routing.
- Root Controller cannot self-promote.
- Implementer-aware independent verification is preserved and extended to
  domain-level independence.
- The advisory layer (`core/model_policy.py`, `core/model_resolver.py`) is
  untouched and remains read-only/advisory/deterministic.
- Native child allocation stays `HOST_EXTERNAL`; this subsystem only computes
  *requested* endpoint/model/effort triples that flow through the existing,
  unchanged Controller validation path (`core/policy_validator.py`).

Out of scope (later phases): live activation triggers, wrapper migration,
deployment to `~/.agents`/`~/.codex`, changes to `models.yaml`.

## 2. Modes

### 2.1 Mode is persistent user intent

Exactly two modes exist:

| Mode | Meaning |
|---|---|
| `sol_mode` | GPT Plus (Sol/Luna) family fully eligible |
| `grok_mode` | Entire `gpt_plus` failure domain excluded from all selection |

Properties (normative):

1. **MANUAL_ONLY:** Mode changes exclusively through explicit operator action
   (`scripts/orchestrator_mode.py set sol|grok`). No code path may change the
   persisted mode as a side effect of runtime events.
2. **PERSISTENT:** The selected mode survives process exit, missions, reboots.
   State lives at `~/.agents/runtime-routing/mode.json`.
3. **HEALTH_CANNOT_SWITCH_MODE:** Runtime health logic may mark a failure
   domain temporarily unhealthy and exclude it from dispatch. It MUST NOT
   write a different mode. Example: in SolMode, a confirmed account-level
   quota failure on `openai_plus_capacity` sets
   `gpt_plus = temporarily unhealthy`; Sol and Luna are then excluded from
   dispatch until cooldown expiry, but the persisted mode remains `sol_mode`
   until the operator explicitly selects GrokMode.
4. **DEFAULT:** A missing/corrupt state file resolves to `sol_mode` with a
   recorded anomaly; first-run initialization writes `sol_mode` explicitly.

### 2.2 SolMode semantics

- Boss chain (priority/failover, NOT weighted):
  1. `SOL_HIGH` (GPT-5.6 Sol High) — preferred when `gpt_plus` healthy
  2. `GROK_4_6_HIGH`
  3. `OPUS_4_6_THINKING`
  4. `GEMINI_FLASH_HIGH`
- Once bound, Boss continuity is mandatory (`DEDICATED_BOSS_CONTINUITY_REQUIRED`,
  unchanged). Health-based exclusion applies only at binding time.
- Sol is never eligible as Standard Worker or normal Deep Worker throughput.

### 2.3 GrokMode semantics

- The `gpt_plus` failure domain (Sol High, Luna Max, Luna xhigh) has **zero
  eligibility** in every role, including Boss.
- Boss chain (priority/failover, NOT weighted):
  1. `GROK_4_6_HIGH`
  2. `OPUS_4_6_THINKING`
  3. `GEMINI_FLASH_HIGH`

### 2.4 Boss binding integration

The existing wrappers hard-bind `sol-luna-orchestrator-v2 → SOL_HIGH` and
`grok-orchestrator-v2 → GROK_4_6_HIGH`. They are not deleted or modified before
the activation task. Mode affects Boss selection through a new shadow-mode
eligibility function:

```python
boss_chain(mode: RoutingMode) -> tuple[EndpointId, ...]
```

returning the ordered chains of §2.2/§2.3 filtered by current health state. In
shadow mode this output is logged alongside the legacy hard binding without
altering submitted requests. At activation (plan Task 12), the skill invocation
surface gains explicit `SolMode`/`GrokMode` triggers; the legacy wrappers remain
as compatibility fallbacks with documented rollback behavior.

## 3. Failure Domains

Selection eligibility and health are tracked per failure domain. Domains are
explicit declarations in configuration; they are never inferred from model
strings (consistent with `docs/PROVIDER_AVAILABILITY.md` "No Provider Inference").

| Domain | Endpoints |
|---|---|
| `gpt_plus` | `SOL_HIGH`, `PLUS_LUNA` (Luna Max), `PLUS_LUNA_XHIGH` (Luna xhigh) — one shared resource domain |
| `gemini` | `GEMINI_FLASH_HIGH` (`google_ag_capacity`) |
| `supergrok` | `GROK_4_6_HIGH` (`xai_gcli_capacity`) |
| `opus` | `OPUS_4_6_THINKING` (`claude_opus_ag_capacity`, CAPACITY_RELATION_UNKNOWN to gemini's domain) |
| (independence only) | `OCG_LUNA` sits in `opencode_go_capacity`, NOT in `gpt_plus`; it is excluded from GPT-implementer review solely via the `gpt_family` independence group (§5.8 stage 2) |
| `cheap` | `STEP_3_7_FLASH` (`nine-router/stepplan/step-3.7-flash`) |
| `ox_combo` | `OX_ALPHA` (`nine-router/OX-ALpha`) |

Normative rules:

1. **SHARED_GPT_DOMAIN:** Marking `gpt_plus` unhealthy excludes Sol AND both
   Luna effort variants simultaneously.
2. **CX_ROUTES_EXCLUDED:** `nine-router/cx/gpt-5.6-sol` and
   `nine-router/cx/gpt-5.6-luna` consume the same underlying ChatGPT Plus
   resource domain as GPT Plus; they are NOT independent capacity and MUST NOT
   appear as candidates anywhere in the routing tables.
3. Domain health is transient runtime state plus an operator-visible status
   view; it never persists a mode change.

## 4. Global Usage Targets (Telemetry Only)

Rolling global token-share targets, used **only** for telemetry reporting:

| Pool | Target |
|---|---|
| Gemini 3.7 Flash High | 45% |
| SuperGrok 4.6 High | 25% |
| GPT Plus Pool (Sol/Luna) | 17% |
| Step / cheap routes | 7% |
| Claude Opus 4.6 Thinking | 6% |

Constraints:

1. Targets NEVER force any role's weights to match global percentages.
   Example: Sol is the preferred SolMode Boss even though `gpt_plus` targets
   17%, because planner token volume is small relative to total spend.
2. The target-share report compares observed rolling distribution against these
   numbers and reports deltas only; it has no enforcement loop.

## 5. Role Weight Tables

All selections within a role use deterministic weighted selection (§6).
Weights are declared per mode in `config/runtime-routing.yaml`; each role table
must sum to exactly 100 (validated at load).

Prohibitions enforced structurally by table content AND by schema validation:
- SCOUT must not contain Grok, Sol, or Opus entries (either mode).
- STANDARD_WORKER must not contain Sol (either mode).
- DEEP_WORKER must not contain Sol (either mode).
- GrokMode tables must not contain any `gpt_plus` endpoint.

### 5.1 SCOUT — SolMode

| Candidate | Weight |
|---|---|
| Gemini High | 70 |
| Luna Max | 20 |
| Step 3.7 Flash | 10 |

### 5.2 SCOUT — GrokMode

| Candidate | Weight |
|---|---|
| Gemini High | 87.5 |
| Step 3.7 Flash | 12.5 |

### 5.3 STANDARD_WORKER base — SolMode

| Candidate | Weight |
|---|---|
| Gemini High | 50 |
| Luna Max | 35 |
| Step 3.7 Flash | 15 |

### 5.4 TEMPORARY OX WORKER OVERLAY — SolMode

When the OX overlay is active, Standard Worker weights become:

| Candidate | Weight |
|---|---|
| OX-ALpha | 30 |
| Gemini High | 35 |
| Luna Max | 25 |
| Step 3.7 Flash | 10 |

Rationale: the currently verified OX combo shows basic PASS, streaming PASS,
tools PASS, strict schema PASS, multi-turn PASS, compaction PASS after one
retry, intermittent 503 and 429, and slow/highly variable latency; therefore
its initial weight is 30, not 70.

### 5.5 TEMPORARY OX WORKER OVERLAY — GrokMode

Explicit policy (NOT derived by accidental normalization):

| Candidate | Weight |
|---|---|
| OX-ALpha | 30 |
| Gemini High | 55 |
| Step 3.7 Flash | 15 |

### 5.5a STANDARD_WORKER base — GrokMode

| Candidate | Weight |
|---|---|
| Gemini High | 75 |
| Step 3.7 Flash | 25 |

This base table is REQUIRED and contains NO OX entry: with
`ox_overlay: disabled`, or `auto` while the `ox_combo` domain is in cooldown,
GrokMode Standard Worker dispatch resolves against this table, so OX can
disappear in GrokMode without code changes. It is an explicit declaration,
never derived by removing the OX row from §5.5 and renormalizing. Sum: 100.
Phase-0 design choice: the 75/25 split is the operator-approved baseline;
it extrapolates SolMode's Gemini-dominant base posture into the GPT-less
pool. The operator MAY override these two numbers in
`config/runtime-routing.yaml` before activation; schema validation only
requires non-negative weights summing to exactly 100.

### 5.6 DEEP_WORKER — SolMode

| Candidate | Weight |
|---|---|
| Grok High | 60 |
| Gemini High | 25 |
| Luna xhigh | 10 |
| Step 3.7 Flash | 5 |

Sol MUST NOT appear in normal Deep Worker throughput. Sol may participate only
as high-value planner/escalation critic under separate policy outside these
routing tables.

### 5.7 DEEP_WORKER — GrokMode

| Candidate | Weight |
|---|---|
| Grok High | 67 |
| Gemini High | 28 |
| Step 3.7 Flash | 5 |

### 5.8 REVIEWER (implementer-aware, not ordinary weighted)

Reviewer selection is a five-stage ordered pipeline; it is never a plain
weighted choice over one fixed table:

```
candidate construction
→ implementer independence-group exclusion
→ mode eligibility
→ health eligibility (capacity-domain lookup)
→ weighted selection (over survivors)
```

Stage 2 uses one explicit group map (`independence_groups` in
`config/runtime-routing.yaml`, group id → member endpoints; shipped groups:
`gpt_family`, `supergrok`, `gemini`, `opus`, `cheap`, `ox_combo` — every
registry endpoint belongs to exactly one group): every GPT-family endpoint — `SOL_HIGH`,
`PLUS_LUNA`, `PLUS_LUNA_XHIGH`, `OCG_LUNA`, and any future
`nine-router/cx/gpt-5.6-*` route — maps to the single group `"gpt_family"`.
A candidate sharing ANY group with the implementer is excluded, so a Sol
implementer can never be verified by any Luna variant (including OCG_LUNA,
whose capacity domain differs), satisfying the critical invariant.
Capacity-domain membership is consulted ONLY at stage 4 for health
filtering — it is never a reviewer-exclusion stage. Group membership is data,
extensible without code change.

Weight tables over survivors (weights renormalize over survivors). Rows key
on the implementer's INDEPENDENCE GROUP — the `gpt_family` row covers
`SOL_HIGH`, all Luna variants, AND `OCG_LUNA` (same group, different capacity
domains):

| Implementer independence group | Mode | Surviving candidates → weights |
|---|---|---|
| `gpt_family` (Sol, any Luna incl. OCG_LUNA) | either | Grok High 65, Gemini High 25, Opus 10 |
| `supergrok` | `sol_mode` | Gemini High 60, Opus 20, Luna 20 |
| `supergrok` | `grok_mode` | Gemini High 75, Opus 25 |
| `gemini` | `sol_mode` | Grok High 60, Luna 25, Opus 15 |
| `gemini` | `grok_mode` | Grok High 75, Opus 25 |
| `cheap` or `ox_combo` | either | Grok High 60, Gemini High 30, Opus 10 |

If exclusion + mode + health filters leave zero candidates, reviewer selection
fails closed with `REVIEWER_CHAIN_EXHAUSTED` (mirrors Core §6C); self-verification
is never permitted to escape exhaustion.

## 6. Deterministic Weighted Selection

Nondeterministic random selection is prohibited. The selector is pure,
stateless, and pinned to ONE algorithm:

**Stable-hash single-bucket cumulative walk.**

```python
import hashlib

def weighted_select(candidates: Sequence[str],
                    weights: Sequence[float],
                    key: SelectionKey) -> str:
    """key = canonical rendering of (mode, mission_id, role, ordinal)."""
    total = sum(weights)                      # validated > 0 at config load
    digest = hashlib.sha256(key.canonical_bytes()).digest()
    u = int.from_bytes(digest[:8], "big") / 2**64        # uniform [0, 1)
    threshold = u * total
    cumulative = 0.0
    for candidate, weight in zip(candidates, weights):
        cumulative += weight
        if threshold < cumulative:
            return candidate
    return candidates[-1]   # float-tail guard only; unreachable in exact math
```

Exactly one hash of the canonical key produces one uniform value `u ∈ [0,1)`;
the ordered candidate list is walked once, accumulating weights until the
cumulative mass first exceeds `u × total`. There is NO per-candidate hashing
and NO last-entry fallback that could skew the categorical distribution.

Normative properties (each enforced by tests):

1. **DETERMINISM:** identical `(mode, mission_id, role, ordinal)` always yields
   the identical candidate, on every machine, in every process.
2. **DISTRIBUTION:** across many distinct ordinals, empirical frequency of each
   candidate converges to weight/total within statistical tolerance (e.g.
   10,000 draws, ±2% absolute for weights ≥ 10, asserted in tests).
3. **STABILITY:** ordinals are independent; adding later dispatches does not
   change earlier selections.
4. **NO STATE:** no counters, no RNG seeding, no cross-process coordination.
5. **KEY DIMENSIONS:** the canonical key includes at minimum `mode`,
   `mission_id`, `role`, and dispatch ordinal / stable packet ordinal. Mode
   additionally determines the weight table itself.

Edge behavior: zero-weight candidates are skipped by construction (a zero-mass
bucket is never selected); an empty candidate list raises before selection;
negative weights are rejected at config load, never at call time.

## 7. Health / Cooldown Model

A dedicated module maintains per-domain transient state, separate from mode
state:

- States per failure domain: `ELIGIBLE` | `COOLDOWN(until_utc)`.
- Triggers (recorded by Controller evidence handling, extending — not replacing
  — Core §10 mission breakers): confirmed account-level quota exhaustion
  (403 usage-limit class) on a domain opens a cooldown for that domain only;
  intermittent 429/5xx/timeouts record telemetry but never open cooldowns
  (consistent with Core §10 "Non-Breaker Events").
- Cooldowns expire automatically; expiry restores eligibility without any mode
  mutation.
- Health state persists at `~/.agents/runtime-routing/health.json`
  (operator-inspectable, safe to delete; deletion means full eligibility).
- Mission-scoped Core §10 breakers continue unchanged and independently;
  dispatch requires passing BOTH layers.

## 8. Routing Telemetry

Append-only JSONL evidence at
`~/.agents/runtime-routing/routing-telemetry.jsonl` recording per dispatch:
timestamp, mode, role, selected endpoint + its independence group + capacity
domain, implementer independence group (verifier rows), `excluded_unverified`
list when §13.1 filtering applied, overlay flag, mission_id, ordinal, latency
class, and outcome class. An aggregation command produces the §4 target-share
report (observed vs target, delta-only). Telemetry is evidence, never control
flow: no selection path reads it. Security: same redaction discipline as
Mission Trace — no secrets; identifiers sanitized and bounded per
`model_availability.sanitize_identifier` conventions.

## 9. OX Overlay Switch

The OX worker overlay is governed by one explicit tri-state setting in
`config/runtime-routing.yaml` (environment-level override allowed):

| Value | Behavior |
|---|---|
| `enabled` | Overlay weights apply whenever the mode table loads |
| `disabled` | Base weights apply; OX never selected |
| `auto` | Overlay applies only while `ox_combo` domain is ELIGIBLE; sustained cooldown suppresses it |

Switching between the three states requires only a config edit — no code
change, no redesign. Default at activation: `auto`.

## 10. Relationship to Existing Architecture

1. **Advisory resolver untouched:** `core/model_policy.py` (four public logical
   roles) and `core/model_resolver.py` remain read-only, offline,
   deterministic, advisory. The runtime layer does not import them for
   selection and does not modify them; their docstring contracts stay literally
   true.
2. **Core policy validator reused, not bypassed:** Every computed
   (endpoint, model, effort) triple passes the existing
   `PolicyValidator.validate_controller_execution_binding` gate before Host
   submission. The new layer proposes requests; the existing layer still
   validates them. Registry additions (`STEP_3_7_FLASH`, `PLUS_LUNA_XHIGH`,
   `OX_ALPHA`) extend `ORCHESTRATOR_CORE.md`'s registry during implementation
   with canonical model strings and accepted efforts consistent with §11.
3. **Host boundary unchanged:** Nothing here claims Host-internal allocation,
   interception, pre-allocation authorization, or non-bypassability. All
   guarantees remain "a conforming Controller does not submit invalid
   requests." Requested ≠ effective identity; trace `UNPROVEN` discipline
   applies to every actual-model observation.
4. **Boss continuity unchanged:** Mode influences which Boss is requested at
   mission start (shadow first). Mid-mission the bound Boss persists; health
   exclusions affect subsequent child dispatches, never Boss rebinding.
5. **models.yaml untouched:** The four-role advisory config keeps its schema,
   location, and semantics. New declarative weights live only in
   `config/runtime-routing.yaml`.
6. **Wrapper compatibility:** Existing skills keep working unchanged during
   shadow mode. Activation adds user-facing `SolMode`/`GrokMode` trigger
   phrases mapping to mode-checked Boss chains; rollback restores legacy
   wrapper bindings without code changes (wrappers retained).

## 11. Identity Audit Basis (exact local facts at baseline `5bf2e25`)

| Logical name | Endpoint ID | Canonical model string | Effort used | Failure domain | Agent declaration |
|---|---|---|---|---|---|
| GPT-5.6 Sol High | `SOL_HIGH` | `gpt-5.6-sol` | high (boss binding) | gpt_plus | default agent (boss binding; no leaf TOML needed) |
| GPT-5.6 Luna Max | `PLUS_LUNA` | `gpt-5.6-luna` | max | gpt_plus | exists: `agents/luna_max_worker.toml` (`luna_max_worker`, effort max) |
| GPT-5.6 Luna xhigh | `PLUS_LUNA_XHIGH` (NEW id) | `gpt-5.6-luna` | xhigh | gpt_plus | none yet; requires either new TOML or effort override — gated on acceptance check below |
| Gemini 3.7 Flash High | `GEMINI_FLASH_HIGH` | `nine-router/ag/gemini-3.7-flash-high` | high | gemini | exists: `router_nine_router_ag_gemini_3_7_flash_high` |
| Grok 4.6 High | `GROK_4_6_HIGH` | `nine-router/gcli/grok-4.6-high` | high | supergrok | boss binding; router/default agent |
| Claude Opus 4.6 Thinking | `OPUS_4_6_THINKING` | `nine-router/ag/claude-opus-4-6-thinking` | high | opus | exists: `router_nine_router_ag_claude_opus_4_6_thinking` |
| Step 3.7 Flash | `STEP_3_7_FLASH` (NEW registry id) | `nine-router/stepplan/step-3.7-flash` | default/high per accepted list | cheap | declaration exists: `router_nine_router_stepplan_step_3_7_flash` (not yet in Core registry) |
| nine-router/OX-ALpha | `OX_ALPHA` (NEW) | `nine-router/OX-ALpha` | provider default | ox_combo | **MISSING — new managed agent TOML required** |
| GPT-5.6 Luna (router route) | `OCG_LUNA` | `opencode-go-responses/gpt-5.6-luna` | high (`policy_max_effort: high`) | opencode_go capacity; independence group `gpt_family` | exists: `router_opencode_go_responses_gpt_5_6_luna`; NOT a routing candidate in any weight table (listed for reviewer-independence completeness) |

Registry facts constraining the design:

- `SOL_HIGH.accepted_efforts` documents `[low, medium, high, xhigh, max, ultra]`.
- `PLUS_LUNA.accepted_efforts` documents `[low, medium, high, max]` — **`xhigh`
  is NOT documented for Luna**. `PLUS_LUNA_XHIGH` therefore requires upstream
  acceptance verification before its registry entry lands (plan Task 6 gate).
  Until then it stays unregistered and the single coherent rule of §13.1
  applies: unverified endpoints are filtered from the candidate list BEFORE
  the one deterministic selection; survivors renormalize through the §6 walk;
  selection refuses (`POLICY_ENDPOINT_UNVERIFIED` → empty candidate set) ONLY
  if no eligible survivor remains. NO substitution, NO retry/redraw.

## 12. Deployment Posture

- **Shadow-first:** All selection machinery runs and logs ("shadow") alongside
  legacy chains with zero submitted-request change until acceptance gates pass
  (plan Task 11).
- **Rollback:** Activation flips are trigger/config-level; rollback restores
  legacy wrapper behavior without code changes (legacy wrappers retained).
- Phase 0 ships documentation only: no runtime files, no installer changes, no
  `~/.agents` writes, no `models.yaml` edits.

## 13. Self-Review Record

Contradiction scan performed against the approved mission text:

- **FOUND AND RESOLVED:** The first draft of §11 stated an unverified Luna
  xhigh share "routes to Luna Max instead". That is silent endpoint
  substitution, contradicting Core's `REJECT_CONTROLLER_SUBSTITUTION`
  doctrine. §13.1 Amendment A now defines the single coherent rule:
  pre-selection exclusion of unverified endpoints, survivor renormalization,
  refusal only on an empty survivor set.
- **FOUND AND RESOLVED (independent review):** GrokMode STANDARD_WORKER had an
  overlay table (§5.5) but no base table, leaving `disabled`/`auto`-off
  undefined in GrokMode. Added explicit non-OX base table §5.5a
  (Gemini 75 / Step 25), design choice documented inline.
- Weight sums: 70+20+10=100; 87.5+12.5=100; 50+35+15=100; 30+35+25+10=100;
  30+55+15=100; 75+25=100 (§5.5a); 60+25+10+5=100; 67+28+5=100; reviewer rows
  65+25+10=100, 60+20+20=100, 75+25=100, 60+25+15=100, 60+30+10=100. OK.
- Sol-as-worker prohibition vs SolMode Boss chain: disjoint planes. OK.
- Reviewer table lists post-exclusion survivors only; Luna column absent from
  GPT-implementer rows because the family rule removes it. OK.
- MANUAL_ONLY mode vs `auto` OX overlay: overlay gating toggles weights only,
  never the persisted mode. OK.
- Global 17% GPT Plus target vs Sol-preferred Boss: resolved by §4 constraint
  1 (telemetry-only targets; planner-volume rationale). OK.
- Health cooldown vs Core §10 non-breaker events: cooldown triggers restricted
  to confirmed account-level quota exhaustion. OK.
- Health reconciled with OX `auto` gating: `auto` consults the SAME
  domain-eligibility state as dispatch (ox_combo ELIGIBLE ⇒ overlay active);
  a transient non-breaker error never suppresses the overlay, only an actual
  ox_combo cooldown does. MANUAL_ONLY untouched — eligibility affects weights,
  never the persisted mode. OK.

### 13.1 Amendment A — Luna xhigh fail-closed rule (post-write review)

The approved Deep Worker (SolMode) table declares `PLUS_LUNA_XHIGH` at
weight 10. Because `PLUS_LUNA.accepted_efforts` does not document `xhigh`,
the following is normative:
- **The rule (single, coherent):** Until upstream acceptance of `xhigh` for
  Luna is verified and `PLUS_LUNA_XHIGH` is registered, unverified endpoints
  are filtered from the candidate list BEFORE the one deterministic selection.
  Surviving weights renormalize through the §6 cumulative walk (one hash, one
  walk): Deep Worker/SolMode then resolves over Grok 60 / Gemini 25 /
  Step 5 (sum 90 → normalized shares 2/3, 5/18, 1/18). Selection raises
  `POLICY_ENDPOINT_UNVERIFIED` ONLY in the degenerate case where filtering
  leaves an empty candidate set. There is NO substitution to Luna Max or any
  other endpoint (Core `REJECT_CONTROLLER_SUBSTITUTION` doctrine), and NO
  retry/redraw of a completed draw.
- **Auditability:** every dispatch made under this rule records
  `excluded_unverified: [PLUS_LUNA_XHIGH]` in telemetry, so the deviation from
  the approved table is explicit and reversible the moment upstream
  verification lands.
- **Removal is the alternative:** If the operator prefers the emitted table to
  equal the approved table exactly during the unverified window, removing the
  entry is an explicit, separately approved config edit — the edited table
  must itself sum to 100 under schema validation.
