# Orchestrator Doctor

Doctor is a read-only report command. Run it from the repository root:

```bash
python3 scripts/doctor.py
```

The command validates the repository-relative [`config/models.yaml`](../config/models.yaml)
by default. `--config PATH` selects another declarative configuration file,
and `--target-home PATH` selects the Codex environment whose local declarations
are inspected:

```bash
python3 scripts/doctor.py --config /path/to/models.yaml
python3 scripts/doctor.py --target-home /path/to/home
```

Doctor validates the exact declarative schema: the roles `planner`, `scout`,
`worker`, and `reviewer`; each role's `requires`, `preferred`, `fallback`, and
`capability_hints` fields; and non-empty lists of non-empty strings. It keeps
the configured role and list order. Invalid, missing, unreadable, or
unparseable configuration exits non-zero and prints an `ERROR:` on stderr.

Valid output is a readable summary, for example:

```text
Orchestrator Doctor
Configuration: valid
Values shown are recommendations/configuration only; discovery does not select models.

Role: planner
  Requires: decision-plane planning; structured task decomposition
  Preferred models: example/model-a
  Fallback models: example/model-b
  Capability hints: long-context reasoning

Discovery (read-only declarations; no provider or runtime probing):
Discovery source codex-profiles: AVAILABLE (1 model(s))
Discovery source codex-agents: UNAVAILABLE (source directory not found)
Configured model comparison:
  Role: planner
    example/model-a: declared
    example/model-b: configured but not declared

Capability metadata and compatibility are advisory only.
They do not prove provider health, authentication, entitlement, runtime availability, effective identity, authorization, or suitability.
Built-in profiles are descriptive defaults; capability_hints remain user-owned advisory labels.
Unknown model metadata is reported as UNKNOWN/metadata-unavailable, never as incompatible.

Role: planner capability analysis
  Advisory hints (config.planner.capability_hints): reasoning; long_context
  gpt-5.6-sol: KNOWN/builtin-profile
    Capabilities: reasoning, coding, long_context, analysis, review
    Provenance: builtin-profile
    Compatibility: COMPATIBLE

Role resolutions (deterministic evaluation via core.model_resolver):
Evaluates exact configured candidates through hard constraints before advisory ranking.
  Role planner: outcome=UNRESOLVED resolved_model=none
    candidate=example/model-a outcome=UNRESOLVED reason=availability-unknown score=none
    candidate=example/model-b outcome=REJECTED reason=not-discovered score=none
```

## Model intelligence cache

`--intelligence-cache PATH` selects an offline Model Intelligence cache. When
the option is omitted, Doctor reads
`TARGET_HOME/.codex/model-intelligence.yaml`, where `TARGET_HOME` is the value
of `--target-home` (or the current user's home by default):

```bash
python3 scripts/doctor.py --target-home /path/to/home \
  --intelligence-cache /path/to/model-intelligence.yaml
```

The cache is a strict local schema version `1`: it requires top-level
`schema_version: 1`, `evidence: [...]`, and `models: [...]`. Evidence entries
contain `id`, `source_type`, `strength`, `locator`, `observed_at`, and
`summary`, with optional `expires_at`. Model entries contain exact `identity`
and `claims`; claims contain `capability`, integer `score` (`0..10`),
`confidence`, and non-empty `evidence_ids`. The loader uses safe YAML parsing,
checks timestamps and evidence references, and never dereferences a locator.
The complete contract and a fictional, inert example are in
[`MODEL_CONFIGURATION.md`](MODEL_CONFIGURATION.md).

Doctor reports these cache states:

- `MISSING`: the selected cache does not exist.
- `INVALID`: it cannot be read or parsed, or fails the schema/value checks.
- `VALID`: it loads and produces profiles from the schema-v1 registry.

For a valid cache, Doctor joins profiles to discovered model declarations by
exact raw identity only. A discovered identity with no exact cache profile is
reported as profile `UNKNOWN`. A valid cache profile with no exact discovered
identity is `NOT_DISCOVERED` and is excluded from recommendations. The derived
display identity is Unicode NFKC plus `strip()` only; it is display metadata and
never alias inference. Raw identity spelling, including meaningful whitespace,
remains authoritative.

Profile status is `ACTIVE`, `STALE`, `CONFLICTED`, or `UNKNOWN`. Expired
evidence is stale; future or absent evidence is unknown; and conflicting claims
for one capability are conflicted. Conflicting scores are withheld, never
averaged. Evidence strength and claim confidence are independent
`LOW`/`MEDIUM`/`HIGH` categories. Confidence maps to fixed advisory arithmetic
values `0.25`/`0.50`/`0.90`; these values are not calibrated probabilities.

Doctor can print deterministic recommendations for discovered `ACTIVE`
profiles. The gate is at least `50%` fixed role-weight coverage. Ties sort by
weighted score descending, coverage descending, mapped confidence descending,
then exact raw identity ascending. Intelligence recommendation records are descriptive ranking only; recommendations alone cannot select, route, allocate, spawn, mutate, remotely probe, alias, or override Core/Host (distinct from the separate deterministic offline advisory Role Resolution section below).

`config/models.yaml` is authoritative for the four logical roles and their
`requires`, ordered `preferred`, ordered `fallback`, and `capability_hints`
values. Intelligence metadata is advisory and cannot override that file or the
RC3 request-contract registry in [`MODELS.md`](MODELS.md).

## Discovery sources and failure behavior

Doctor reads only top-level `model` strings from these sources under the
selected target home:

- `codex-profiles`: `.codex/*.config.toml`
- `codex-agents`: `.codex/agents/*.toml`

A missing directory, no matching declaration files, a matching non-file path,
an unreadable file, or malformed TOML makes that source `UNAVAILABLE`.
For successfully parsed TOML declarations, if an individual declaration contains
a non-string or `strip()`-empty `model` value, only that invalid declaration is skipped,
invalid declarations are counted in the static safe detail (e.g. `2 model(s), 1 invalid declaration(s)`),
and valid sibling declarations survive in deterministic path order. If all parsed declarations
contain semantic invalid models, the source is reported `UNAVAILABLE (no valid declarations)`.
Discovery sources are independent: one unavailable source does not hide results from the
other. An unavailable source never changes successful configuration validation
into an error, so a structurally valid configuration still exits zero.

Comparison uses exact strings from `preferred` and `fallback`; it does not
normalize provider names or aliases. `declared` means only that the exact
identifier appeared in at least one readable declaration source. `configured
but not declared` means no readable source contained that exact string. Neither
status is a provider-health, authentication, entitlement, quota, or
runtime-allocation claim. Capability metadata likewise uses exact model
identifiers and stable labels (`reasoning`, `coding`, `fast`, `long_context`,
`analysis`, `review`, and `cost_effective`). Built-in profiles are descriptive
defaults only; they are not permissions or selection rules. Existing
`capability_hints` are user-owned advisory labels and are preserved as written.
Known metadata may be reported `COMPATIBLE` or `INCOMPATIBLE` against those
hints, while missing metadata is always `UNKNOWN/metadata-unavailable`, never
incompatible.

These capability and compatibility statuses do not prove provider health,
authentication, entitlement, runtime availability, effective identity,
authorization, or suitability. They do not select, resolve, assign, route, or
spawn a model.

## Model availability and active probes

Doctor includes a read-only model availability and provider health section:

- By default, Doctor executes zero active probes and reports static offline observations as `UNKNOWN` (`offline-declaration`).
- Passing `--active-probes` explicitly requests active probing. However, because no active provider probe adapter is currently supported or configured in this environment, Doctor reports `UNKNOWN` (`probe-unsupported`) without executing any network or subprocess calls.
- Model availability (`AVAILABLE`, `UNAVAILABLE`, `UNKNOWN`) and provider health (`HEALTHY`, `UNAVAILABLE`, `UNKNOWN`) are strictly separated from configured, declared, and capability states. Configuration and discovery declarations do not imply `AVAILABLE` or `HEALTHY`.
- Provider identity is explicit or `UNKNOWN`. Doctor never infers provider identities from model identifier prefixes.
- Freshness tracking uses explicit `FRESH`, `STALE`, or `UNKNOWN` categories. There is no separate health cache distinction.
- Identifiers across configured, discovered, capability, intelligence, and availability outputs are sanitized and bounded against control-character, escape sequence (ANSI), and newline injection using a shared bounded sanitizer (`sanitize_identifier`). Backslashes render escaped as valid content and strings are deterministically bounded at <=384 display characters with a stable truncation marker (`...`), preventing raw full overlong identifier leakage. Complete Doctor rendered output lines are capped at <=512 characters by a shared line joiner.

### Probe-Source Matrix

| Source / Scope | Source Type | Side Effects | Support Level | Reported State | Provenance |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `config/models.yaml` | Static config | None (read-only file parse) | Supported | Role preferred/fallback lists | `configured` |
| Local Codex TOML (`.codex/*.toml`) | Local filesystem | None (read-only declaration parse) | Supported | Discovered model strings | `codex-profiles` / `codex-agents` |
| Built-in capabilities | In-memory registry | None (pure lookup) | Supported | Advisory capability tags | `builtin-profile` |
| Intelligence cache (`model-intelligence.yaml`) | Local offline cache | None (read-only YAML parse) | Supported | Advisory score/confidence claims | `fixture` / offline evidence |
| Provider APIs (Remote HTTP endpoints) | Network / Remote API | Prohibited (zero network) | Unsupported | `UNKNOWN` (`PROBE_UNSUPPORTED`) | `probe-unsupported` |
| Host / router runtime | Subprocess / IPC | Prohibited (zero execution) | Unsupported | `UNKNOWN` (`PROBE_UNSUPPORTED`) | `probe-unsupported` |
| Active probe adapters (Injected test seam) | Pure callable seam | In-memory test mock only | Supported in test | Invariant-validated record | `active-probe` |

### Live Validation Table

| Validation State | Condition / Meaning | Authority & Route Evidence |
| :--- | :--- | :--- |
| **PROVEN** | Point-in-time reachability confirmed via explicit active probe adapter with verified `FRESH` freshness, timezone-aware timestamp, and measured non-negative latency. | Requires explicit provider binding and verified execution response. Never inferred from configuration or capability hints. |
| **UNAVAILABLE** | Probe returned an explicit failure category (e.g. `AUTH`, `RATE_LIMIT`, `SERVER`, `TIMEOUT`) or provider confirmed unreachable. | Grounded in point-in-time probe failure without fabricated error metadata. |
| **UNPROVEN** | Default offline observation or unsupported probe (`UNKNOWN` status, `UNKNOWN` freshness). No live verification performed. | Static declarations, missing adapters, or default Doctor runs without active probe support. |

## Read-only boundary and security gates

Doctor performs deterministic offline advisory role resolution, but never
executes, routes, allocates, spawns, remotely probes, mutates config, or
overrides Core/Host boundaries. It does not execute configured model strings,
run self-evaluation, or read credential values. The cache and local TOML files
are untrusted input: keep secrets out of every field, use inert provenance
locators, and treat all output as descriptive text. HTTP(S) locators are
validated as labels only (credentials in a locator are rejected); no locator is
fetched.

`EXTERNAL_RESEARCH_BOUNDARY: no supported programmatic web-search/external HTTP API exists.`
Reviewed external research may produce only inert, manually reviewed YAML with
provenance and timestamps. There is no supported browsing, fetching, execution,
or model self-evaluation path.

## Deterministic Advisory Resolver Integration

Doctor integrates the deterministic offline resolver (`core/model_resolver.py`, `resolve_role`) into its report. For each role, configured candidate identifiers are evaluated through sequential hard constraints (`exact_configured_identity` → `discovered_identity` → `availability_not_unavailable`), followed by advisory capability compatibility and intelligence profile ranking.

Outcomes reported:
- `RECOMMENDED`: Candidate is discovered, explicitly `AVAILABLE`, capability-compatible, and backed by an `ACTIVE` intelligence profile with sufficient coverage.
- `UNRESOLVED`: Candidate passed hard constraints, but availability is `UNKNOWN` (default offline observation), metadata is unavailable, or intelligence evidence is insufficient.
- `REJECTED`: Candidate is not discovered in any available source, or is explicitly observed as `UNAVAILABLE`.
- `UNKNOWN`: No candidates configured.

This resolver integration is strictly offline and read-only. It does not probe remote providers, mutate files, alter Core routing, or interact with the Host.
