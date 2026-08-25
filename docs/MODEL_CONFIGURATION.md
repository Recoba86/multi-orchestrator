# Declarative Model-Role Configuration

`config/models.yaml` is the authoritative, provider-agnostic configuration
contract for four logical roles: `planner`, `scout`, `worker`, and `reviewer`.

It is intentionally declarative. Configuration semantics are centralized in
`core/model_policy.py`, and evaluated deterministically by the offline advisory
resolver in `core/model_resolver.py`. Doctor performs read-only structural
validation, discovery comparison, capability analysis, availability observation,
intelligence profile joins, and structured role resolution rendering. Safe
explicit mutations can be performed via `configure-models` (`--apply`,
`--approve`, `--expected-sha256`).

The resolver is offline and advisory: it never executes network requests,
probes remote providers, silently overrides configuration, or performs native
Host allocation or spawn (`HOST_EXTERNAL`). Editing this file cannot change
executable RC3 bindings in `core/ORCHESTRATOR_CORE.md`.

## Schema

The YAML root contains exactly the four role names. Each role contains exactly
these four fields, and every field is a non-empty list of non-empty strings:

```yaml
planner:
  requires: ["decision-plane planning"]
  preferred: ["example/model-a", "example/model-b"]
  fallback: ["example/model-c", "example/model-d"]
  capability_hints: ["structured decomposition"]
```

- `requires` describes logical requirements for the role, such as read-only
  review or bounded write ownership.
- `preferred` is an ordered list of optional model-identifier recommendations.
- `fallback` is an ordered list of optional model-identifier recommendations.
- `capability_hints` gives advisory capability labels for future selection.

Unknown top-level keys, role names, or fields are invalid. The schema is tested
by [`tests/test_model_configuration.py`](../tests/test_model_configuration.py).

## Local Model Intelligence cache (schema v1)

Model Intelligence is an offline, descriptive input selected by Doctor. Its
cache requires `schema_version: 1` and top-level `evidence` and `models` lists.
The required entry shapes are:

- An `evidence` entry has `id`, `source_type`, `strength`, `locator`,
  `observed_at`, and `summary`; `expires_at` is optional.
- A `models` entry has an exact raw `identity` and a `claims` list.
- A claim has `capability`, integer `score` from `0` through `10`, a
  `confidence` category, and non-empty `evidence_ids` that resolve into the
  evidence list.

The fixed capability dimensions consumed by current advisory role ranking are
`reasoning`, `coding`, `analysis`, `fast`, `long_context`, `review`, and
`cost_effective`. Additional imported capability labels may remain stored in
the cache, but they do not affect ranking unless they are present in a role
weight map. Evidence strength and claim confidence are independent `LOW`,
`MEDIUM`, or `HIGH` categories. Confidence maps to fixed advisory values
`0.25`, `0.50`, and `0.90`; the mapping is not calibrated. Every
`observed_at`, optional `expires_at`, and evaluation `as_of` timestamp must be
timezone-aware.

The raw identity is authoritative for every join. Doctor derives a display-only
NFKC-plus-`strip()` key; it does not infer aliases, normalize provider names,
or merge distinct raw strings. Profiles are `ACTIVE`, `STALE`, `CONFLICTED`,
or `UNKNOWN`. Expired evidence is stale; future or absent evidence is unknown;
and conflicting values for one capability are withheld rather than averaged.

Recommendations are non-selecting and deterministic: only discovered `ACTIVE`
profiles with at least `50%` fixed role-weight coverage are eligible. Ties sort
by weighted score descending, coverage descending, mapped confidence descending,
then exact raw identity ascending. Profiles present only in the cache are
`NOT_DISCOVERED` and excluded. This cache cannot select, route, allocate,
authorize, or spawn a model.

The following is one syntactically valid schema-v1 fixture. IDs, identities,
and locators are deliberately fictional; it is inert documentation data, not a
provider or capability claim:

```yaml
schema_version: 1
evidence:
  - id: ev-fictional-orchid-reasoning
    source_type: fictional-review
    strength: HIGH
    locator: urn:fictional:orchid:reasoning
    observed_at: "2026-08-25T08:00:00Z"
    expires_at: "2026-12-31T00:00:00Z"
    summary: Synthetic reasoning note for documentation only.
  - id: ev-fictional-orchid-context
    source_type: fictional-review
    strength: MEDIUM
    locator: urn:fictional:orchid:context
    observed_at: "2026-08-25T08:05:00Z"
    summary: Synthetic context note for documentation only.
  - id: ev-fictional-lens-analysis
    source_type: fictional-review
    strength: LOW
    locator: urn:fictional:lens:analysis
    observed_at: "2026-08-25T08:10:00Z"
    summary: Synthetic analysis note for documentation only.
models:
  - identity: fictional/orchid-7
    claims:
      - capability: reasoning
        score: 8
        confidence: HIGH
        evidence_ids: [ev-fictional-orchid-reasoning]
      - capability: long_context
        score: 7
        confidence: MEDIUM
        evidence_ids: [ev-fictional-orchid-context]
  - identity: fictional/lens-2
    claims:
      - capability: analysis
        score: 6
        confidence: LOW
        evidence_ids: [ev-fictional-lens-analysis]
```

## Ordering and provider neutrality

The `preferred` and `fallback` lists are user-editable and order-sensitive.
Doctor preserves and reports the configured values in exact order.
The offline resolver (`resolve_role`) evaluates configured candidates
deterministically through hard constraints before advisory capability and
intelligence ranking. Probing remote providers, automatic routing overrides,
and native Host spawn are not implemented.

Provider/model strings in the file are examples or optional current
recommendations. They are not universal requirements. Replace them with
identifiers declared in the user's local Codex environment when appropriate.

## External-research and security boundary

`EXTERNAL_RESEARCH_BOUNDARY: no supported programmatic web-search/external HTTP API exists.`
Reviewed external research may produce only inert, manually reviewed YAML with
provenance and explicit timestamps. This project has no supported browsing,
fetching, execution, or model self-evaluation path. Do not put credentials,
tokens, private URLs, or other secrets in this file or an intelligence cache.

Doctor uses safe YAML parsing and read-only operations. Cache locators are
provenance labels only and are never fetched; HTTP(S) locators containing
credentials are rejected. Invalid schema, timestamps, scores, categories,
evidence references, or duplicate exact identities fail closed. No cache or
configuration write is performed.

## Resolver and Configuration Mutation Semantics

The resolver (`core/model_resolver.py`, `resolve_role`) adheres to strict safety boundaries:
- **Hard Constraints Before Ranking:** Evaluates `exact_configured_identity` → `discovered_identity` → `availability_not_unavailable` in sequence before any advisory capability/intelligence ranking.
- **UNKNOWN Is Not AVAILABLE:** Offline observations default to `UNKNOWN` (`offline-declaration`). `UNKNOWN` availability yields an `UNRESOLVED` outcome, never `RECOMMENDED`.
- **Evidence Separation:** Status, freshness, provenance, confidence, latency, and timestamp dimensions are strictly separated and never inferred from each other.
- **Deterministic Tie-Breaking:** `RECOMMENDED` candidates sort by `weighted_score` descending, `coverage` descending, `confidence` descending, then exact `raw_identity` ascending.
- **Explicit Approved Mutation (`configure_models.py` / `configure-models`):**
  Safe modification of role preferences is dry-run by default. Applying changes requires explicit `--apply`, `--approve`, and `--expected-sha256 <SHA>` matching the file's current bytes. The mutation creates a collision-safe byte-exact backup (`.bak.<timestamp>_<pid>`), writes atomically via a temporary file in the same directory, syncs to disk, and fails closed on any mismatch or error.

## Relationship to RC3 routing

The existing endpoint registry and role chains in [`MODELS.md`](MODELS.md) are
the current RC3 compatibility profile. They remain concrete request-contract
examples and are not replaced by this file. Native allocation, effective model
identity, and routing enforcement remain Host-external as described in the
[execution boundary](../core/ORCHESTRATOR_CORE.md#execution-boundary-model-host_external--authoritative).
