# SolMode / GrokMode Weighted Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement mode-aware deterministic weighted runtime routing (SolMode/GrokMode) behind a shadow-first deployment with zero change to live orchestration behavior until explicit activation.

**Architecture:** New self-contained runtime routing layer (`core/runtime_routing_*.py`, `scripts/orchestrator_mode.py`, `scripts/route_model.py`, `config/runtime-routing.yaml`) that computes *requested* endpoint/model/effort triples; every triple still passes the existing `core/policy_validator.PolicyValidator` gate. The advisory resolver (`core/model_policy.py`, `core/model_resolver.py`), `config/models.yaml`, wrappers, and installer behavior are untouched until the explicitly gated Task 12.

**Tech Stack:** Python 3 stdlib only (`hashlib`, `json`, `pathlib`, `unittest`, `argparse`; PyYAML already used by existing modules parses `config/runtime-routing.yaml`).

**Spec:** `docs/superpowers/specs/2026-08-26-solmode-grokmode-weighted-routing-design.md` — executors read both documents; the spec is normative for all weights, chains, invariants, and the §13.1 Luna-xhigh fail-closed rule.

## Global Constraints

- Branch: `feat/solmode-grokmode-weighted-routing` from develop `5bf2e25da255e3e66628e8f040b73390bbdc0598`.
- Full suite command at every commit boundary: `python3 -m unittest discover -s tests` — baseline 192 tests OK, exit 0; count may only grow.
- Clean-room lifecycle check after any task touching `agents/` or installer-affecting paths:
  `TMP_HOME="$(mktemp -d)"; ./scripts/install.sh --target-home "$TMP_HOME" && ./scripts/verify.sh --target-home "$TMP_HOME" && ./scripts/uninstall.sh --target-home "$TMP_HOME"; rm -rf "$TMP_HOME"`.
- NEVER modify before Task 12: `core/model_policy.py`, `core/model_resolver.py`, `config/models.yaml`, installed `~/.agents`, `~/.codex`, Codex Router.
- Selector algorithm pinned (spec §6): ONE sha256 of canonical `(mode, mission_id, role, ordinal)` → uniform bucket `u ∈ [0,1)` → single ordered cumulative-weight walk. No per-candidate hashing. No RNG. No counters. Final-entry guard is float-tail only and never constitutes a distributional fallback.
- Mode changes ONLY via operator CLI; no health/telemetry/selection code writes mode state (enforced by grep-guard tests).
- All weights copied verbatim from spec §5; each role table sums to exactly 100 (validated at load).
- `nine-router/cx/gpt-5.6-sol` / `nine-router/cx/gpt-5.6-luna` never appear as candidates anywhere.
- Luna-xhigh fail-closed (spec §13.1): unverified `PLUS_LUNA_XHIGH` is never silently remapped to any endpoint; it is filtered BEFORE the single deterministic walk, survivors renormalize, and selection refuses with `POLICY_ENDPOINT_UNVERIFIED` ONLY when filtering leaves an empty candidate set.
- Tests follow repo convention: `unittest`, one file per module under `tests/`.
- Every task ends with its own commit; no unrelated subsystems combined.

---

### Task 1: Mode state + manual CLI

**Files:**
- Create: `core/runtime_routing_mode.py`
- Create: `scripts/orchestrator_mode.py`
- Test: `tests/test_runtime_routing_mode.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `RoutingMode` enum: `SOL_MODE = "sol_mode"`, `GROK_MODE = "grok_mode"`
  - `MODE_STATE_PATH_DEFAULT: Path` = `~/.agents/runtime-routing/mode.json`
  - `read_mode(state_path: Path = MODE_STATE_PATH_DEFAULT) -> RoutingMode`
    — missing/corrupt/unknown value → `SOL_MODE` plus anomaly sidecar
    `<state_path>.anomaly` recording reason (`missing|corrupt|unknown_value`);
    never raises on bad content.
  - `write_mode(mode: RoutingMode, state_path: Path = MODE_STATE_PATH_DEFAULT) -> None`
    — atomic write (tmp file + `os.replace`), parents created.
  - CLI `python3 scripts/orchestrator_mode.py status|set sol|grok`
    (optional `--state-path`); `set` is the only writer; prints resolved mode
    and state path; exit 0 on success.

- [ ] **Step 1: Write failing tests**

```python
import json, tempfile, unittest
from pathlib import Path
from core.runtime_routing_mode import RoutingMode, read_mode, write_mode

class ModeStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "runtime-routing" / "mode.json"

    def test_missing_state_defaults_sol_and_records_anomaly(self):
        self.assertEqual(read_mode(self.path), RoutingMode.SOL_MODE)
        self.assertTrue(Path(str(self.path) + ".anomaly").exists())

    def test_roundtrip_grok(self):
        write_mode(RoutingMode.GROK_MODE, self.path)
        self.assertEqual(read_mode(self.path), RoutingMode.GROK_MODE)

    def test_corrupt_state_defaults_sol(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(read_mode(self.path), RoutingMode.SOL_MODE)

    def test_unknown_mode_value_defaults_sol(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"mode": "banana"}), encoding="utf-8")
        self.assertEqual(read_mode(self.path), RoutingMode.SOL_MODE)

class ModeCliTests(unittest.TestCase):
    def run_cli(self, *args, home):
        import subprocess, sys, os
        env = dict(os.environ)
        root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [sys.executable, str(root / "scripts" / "orchestrator_mode.py"),
             "--state-path", str(home / "m.json"), *args],
            capture_output=True, text=True, env=env)

    def test_status_then_set_grok_then_status(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            r1 = self.run_cli("status", home=home)
            self.assertEqual(r1.returncode, 0)
            self.assertIn("sol_mode", r1.stdout)
            r2 = self.run_cli("set", "grok", home=home)
            self.assertEqual(r2.returncode, 0)
            r3 = self.run_cli("status", home=home)
            self.assertIn("grok_mode", r3.stdout)
```

- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_routing_mode -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_routing_mode`.

- [ ] **Step 3: Minimal implementation**

`core/runtime_routing_mode.py`: enum, atomic read/write per contract,
anomaly sidecar JSON `{"reason": ..., "observed": ..., "resolved": ...}`.

`scripts/orchestrator_mode.py`: argparse subcommands `status` / `set`;
`set` accepts only `sol`|`grok`, maps to enum values; imports core module.

- [ ] **Step 4: Run tests, verify PASS** — same command, all green.

- [ ] **Step 5: Commit**
```bash
git add core/runtime_routing_mode.py scripts/orchestrator_mode.py tests/test_runtime_routing_mode.py
git commit -m "feat(routing): persistent manual SolMode/GrokMode state + CLI"
```
Acceptance gate: full suite `python3 -m unittest discover -s tests` green;
no other files touched (`git status --short` shows exactly the three files).

### Task 2: Runtime policy schema + validation

**Files:**
- Create: `core/runtime_routing_policy.py`
- Create: `config/runtime-routing.yaml`
- Test: `tests/test_runtime_routing_policy.py`

**Interfaces:**
- Consumes: `RoutingMode` (Task 1).
- Produces:
  - Frozen dataclasses:
    `CandidateWeight(endpoint_id: str, weight: float)`,
    `FailureDomain(name: str, endpoint_ids: tuple[str, ...])`,
    `RuntimePolicy(domains: dict[str, FailureDomain],
      independence_groups: dict[str, tuple[str, ...]],
      boss_chains: dict[RoutingMode, tuple[str, ...]],
      role_weights: dict[tuple[str, RoutingMode, bool], tuple[CandidateWeight, ...]],
      reviewer_tables: dict[tuple[str, RoutingMode], tuple[CandidateWeight, ...]],
      global_targets: dict[str, float],
      ox_overlay: str)`
    where:
    - `independence_groups`: group id → tuple of endpoint ids sharing it.
      Shipped content: `"gpt_family": ("SOL_HIGH", "PLUS_LUNA",
      "PLUS_LUNA_XHIGH", "OCG_LUNA")` — every current and future GPT-family
      endpoint (incl. any `nine-router/cx/gpt-5.6-*` route if ever added)
      MUST map into this single group. One group label per membership set;
      no overlapping family concepts.
    - `reviewer_tables` key[0] is the implementer's INDEPENDENCE GROUP id
      (`"gpt_family"`, `"supergrok"`, `"gemini"`, `"cheap"`, `"ox_combo"`),
      NOT the capacity failure domain. Capacity domains are consulted ONLY by
      reviewer stage-4 health filtering.
    - role key boolean = overlay active.
  - `group_of(policy, endpoint_id: str) -> str` — resolves an endpoint to its
    independence group; raises `PolicyValidationError` for an unmapped
    endpoint (fail closed: an ungrouped endpoint can never be selected as a
    reviewer candidate).
  - `load_runtime_policy(path: Path) -> RuntimePolicy`, raising
    `PolicyValidationError(ValueError)` with message prefix
    `"INVALID_RUNTIME_POLICY: "` on any of: unknown top-level keys; negative
    weights; role table sum ≠ 100 (tolerance 1e-9); Sol endpoint present in
    SCOUT/STANDARD_WORKER/DEEP_WORKER tables (either mode); Grok/Sol/Opus in
    SCOUT tables; any gpt_plus endpoint id in a grok_mode table;
    `nine-router/cx/*` model strings anywhere; unknown `ox_overlay` value
    (allowed: `enabled`, `disabled`, `auto`); reviewer table weights not
    summing to 100; `independence_groups` entry referencing an endpoint id
    absent from `endpoint_resolution`; a `reviewer_tables` key whose group id
    is not a defined independence group; any registry endpoint missing from
    all independence groups.
  - `weights_for(policy, role: str, mode: RoutingMode, ox_overlay_active: bool)
    -> tuple[CandidateWeight, ...]`
  - `boss_chain_for(policy, mode: RoutingMode) -> tuple[str, ...]`

- [ ] **Step 1: Write failing tests**

Cases (each asserts accept or exact rejection prefix + substring):
1. Shipped `config/runtime-routing.yaml` loads successfully into `RuntimePolicy`.
2. Spec §5 weight tables byte-match YAML: scout/sol 70/20/10; scout/grok
   87.5/12.5; worker base/sol 50/35/15; worker overlay/sol 30/35/25/10;
   worker overlay/grok 30/55/15; worker base/grok 70/30 (§5.5a);
   deep/sol 60/25/10+5; deep/grok 67/28+5.
3. Reviewer rows match spec §5.8 for all six (implementer_independence_group,
   mode) keys.
4. Adding `SOL_HIGH` to STANDARD_WORKER sol table → INVALID_RUNTIME_POLICY.
5. Adding `GROK_4_6_HIGH` to SCOUT → rejected.
6. Table summing to 99 → rejected.
7. Candidate string `nine-router/cx/gpt-5.6-sol` → rejected.
8. `boss_chain_for(sol)` == `(SOL_HIGH, GROK_4_6_HIGH, OPUS_4_6_THINKING,
   GEMINI_FLASH_HIGH)`; `boss_chain_for(grok)` == `(GROK_4_6_HIGH,
   OPUS_4_6_THINKING, GEMINI_FLASH_HIGH)`.
9. `ox_overlay: banana` → rejected; three legal values parse.
10. `weights_for(worker, grok, True)` returns the explicit 30/55/15 table and
    `weights_for(worker, grok, False)` returns the explicit 70/30 §5.5a base
    (proves both are declared, not derived).
11. Independence groups: `group_of(policy, "OCG_LUNA") == "gpt_family"`;
    removing the `gpt_family` entry from the YAML → INVALID_RUNTIME_POLICY;
    a `reviewer_tables` key using unknown group `"banana"` → rejected; an
    `independence_groups` member naming endpoint `NOPE_ENDPOINT` (absent from
    `endpoint_resolution`) → rejected.
12. Full coverage: every endpoint in `endpoint_resolution` resolves via
    `group_of` without error; `reviewer_tables["gpt_family", sol]` row equals
    Grok 65 / Gemini 25 / Opus 10 — GPT rows keyed by independence group,
    not capacity domain.

- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_routing_policy -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_routing_policy`.

- [ ] **Step 3: Minimal implementation**

`config/runtime-routing.yaml` schema v1 sections: `schema_version`,
`independence_groups` (group id → endpoint list; shipped:
gpt_family=[SOL_HIGH, PLUS_LUNA, PLUS_LUNA_XHIGH, OCG_LUNA],
supergrok=[GROK_4_6_HIGH], gemini=[GEMINI_FLASH_HIGH],
opus=[OPUS_4_6_THINKING], cheap=[STEP_3_7_FLASH], ox_combo=[OX_ALPHA] —
every endpoint_resolution id MUST appear in exactly one group; any future
cx/gpt-5.6-* route maps into `gpt_family`),
`failure_domains` (capacity domains for health only:
gpt_plus=[SOL_HIGH, PLUS_LUNA, PLUS_LUNA_XHIGH],
gemini=[GEMINI_FLASH_HIGH], supergrok=[GROK_4_6_HIGH], opus=[OPUS_4_6_THINKING],
cheap=[STEP_3_7_FLASH], ox_combo=[OX_ALPHA]), `boss_chains` per spec §2.2–§2.3,
`role_weights` keyed by role→mode→base/overlay, `reviewer_tables` keyed by
implementer_independence_group→mode, `global_targets` (.45/.25/.17/.07/.06),
`ox_overlay: auto`, `endpoint_resolution` map endpoint→(model, effort):
GEMINI_FLASH_HIGH→(nine-router/ag/gemini-3.7-flash-high, high);
PLUS_LUNA→(gpt-5.6-luna, max); PLUS_LUNA_XHIGH→(gpt-5.6-luna, xhigh
[UNVERIFIED — spec §13.1: pre-selection exclusion]); OCG_LUNA→
(opencode-go-responses/gpt-5.6-luna, high); STEP_3_7_FLASH→
(nine-router/stepplan/step-3.7-flash, high); GROK_4_6_HIGH→
(nine-router/gcli/grok-4.6-high, high); OPUS_4_6_THINKING→
(nine-router/ag/claude-opus-4-6-thinking, high); OX_ALPHA→(nine-router/OX-ALpha,
default); SOL_HIGH→(gpt-5.6-sol, high).

`core/runtime_routing_policy.py`: yaml load + frozen dataclasses + validation
per contract (~200 lines, stdlib + PyYAML only).

- [ ] **Step 4: Run tests, verify PASS**
Run: `python3 -m unittest tests.test_runtime_routing_policy -v` then full suite `python3 -m unittest discover -s tests`.
Expected: all green, exit 0.
- [ ] **Step 5: Commit**
```bash
git add core/runtime_routing_policy.py config/runtime-routing.yaml tests/test_runtime_routing_policy.py
git commit -m "feat(routing): validated runtime policy schema and role/pool tables"
```
Gate: shipped YAML passes validation; prohibited-endpoint rejections proven.

### Task 3: Pure deterministic weighted selector

**Files:**
- Create: `core/runtime_weighted_selector.py`
- Test: `tests/test_runtime_weighted_selector.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `SelectionKey(mission_id: str, role: str, ordinal: int, mode: RoutingMode)`
    with `.canonical_bytes() -> bytes` =
    `f"{mode.value}|{mission_id}|{role}|{ordinal}".encode("utf-8")`
  - `weighted_select(candidates: Sequence[CandidateWeight], key: SelectionKey)
    -> CandidateWeight` implementing spec §6 EXACTLY:

```python
import hashlib

def weighted_select(candidates, key):
    if not candidates:
        raise ValueError("EMPTY_CANDIDATES")
    total = sum(c.weight for c in candidates)
    digest = hashlib.sha256(key.canonical_bytes()).digest()
    u = int.from_bytes(digest[:8], "big") / 2**64          # uniform [0,1)
    threshold = u * total
    cumulative = 0.0
    for c in candidates:
        cumulative += c.weight
        if threshold < cumulative:
            return c
    return candidates[-1]   # float-tail guard only
```

  One hash, one uniform bucket, one ordered walk. Zero-weight entries can
  never win (zero-mass bucket). No RNG, no counters, no I/O.

- [ ] **Step 1: Write failing tests**

1. Determinism: same key twice → identical candidate object.
2. Known-vector: for `[(a,50),(b,50)]`, key `(sol_mode,"m1","SCOUT",0)`,
   independently compute expected winner inline in the test from sha256 of
   `"sol_mode|m1|SCOUT|0"` and assert equality.
3. Distribution: `[(g,70),(l,20),(s,10)]`, ordinals 0..9999 fixed mission:
   empirical share within ±0.02 absolute of .70/.20/.10.
4. Stability: result for ordinal 5 unchanged regardless of other ordinals
   computed before/after (order-independence of pure function).
5. Zero-weight candidate never selected across 10,000 draws.
6. Empty list → `ValueError("EMPTY_CANDIDATES")`.
7. 100 distinct mission_ids produce ≥ 2 distinct winners over 70/30 split
   (bucket sensitivity sanity).

- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_weighted_selector -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_weighted_selector`.

- [ ] **Step 3: Minimal implementation** — the pinned algorithm verbatim (~25 lines).

- [ ] **Step 4: Run tests, verify PASS**
Run: `python3 -m unittest tests.test_runtime_weighted_selector -v` (distribution test takes seconds; deterministic).
- [ ] **Step 5: Commit**
```bash
git add core/runtime_weighted_selector.py tests/test_runtime_weighted_selector.py
git commit -m "feat(routing): deterministic stable-hash cumulative weighted selector"
```
Gate: distribution convergence + determinism proven by tests.

### Task 4: Boss mode eligibility/binding integration (shadow)

**Files:**
- Create: `core/runtime_boss_binding.py`
- Test: `tests/test_runtime_boss_binding.py`

**Interfaces:**
- Consumes: `RuntimePolicy.boss_chains` + `boss_chain_for` (Task 2),
  `read_mode` (Task 1), injected `domain_eligible: Callable[[str], bool]`
  (real impl arrives Task 8).
- Produces:
  - `ShadowBossDecision(chain, selected: str | None,
    exclusions: tuple[tuple[str, str], ...])` where exclusions carry reasons
    `HEALTH_COOLDOWN` | `MODE_EXCLUDED_GPT_PLUS`.
  - `shadow_boss_binding(mode: RoutingMode, domain_eligible) ->
    ShadowBossDecision`: walks chain in order; first eligible endpoint wins;
    gpt_plus members of the SOL chain are excluded with
    `MODE_EXCLUDED_GPT_PLUS` when mode == GROK_MODE (defense in depth — chain
    already contains none) or `HEALTH_COOLDOWN` when ineligible via callable.
  - `legacy_binding(skill_name: str) -> str`: constant map returning
    `SOL_HIGH` for `sol-luna-orchestrator-v2`, `GROK_4_6_HIGH` for
    `grok-orchestrator-v2`, else `ValueError`. Wrapper files NOT modified.
  - Shadow-only contract: module performs NO submission, NO Host interaction;
    callers log decisions (wired in Task 9).

- [ ] **Step 1: Write failing tests**: sol chain order matches spec §2.2;
  grok chain matches §2.3 and structurally contains zero gpt_plus endpoints
  even though sol's does; healthy domains → sol selects SOL_HIGH; gpt_plus
  cooldown in sol_mode → skips to GROK_4_6_HIGH with recorded exclusion;
  grok_mode ignores health entirely for gpt_plus (absent by construction);
  legacy map equals current wrapper bindings verbatim; decision is immutable
  (frozen dataclass).
- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_boss_binding -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_boss_binding`.
- [ ] **Step 3: Minimal implementation** (~60 lines, pure functions, frozen dataclass).
- [ ] **Step 4: Run tests, verify PASS**
Run: `python3 -m unittest tests.test_runtime_boss_binding -v` then `python3 -m unittest discover -s tests`.
- [ ] **Step 5: Commit**
```bash
git add core/runtime_boss_binding.py tests/test_runtime_boss_binding.py
git commit -m "feat(routing): shadow-mode Boss eligibility/binding computation"
```
Gate: full suite green; commit contains only these two files.

### Task 5: Scout/Standard Worker/Deep Worker dispatch

**Files:**
- Create: `core/runtime_role_dispatch.py`
- Test: `tests/test_runtime_role_dispatch.py`

**Interfaces:**
- Consumes: Tasks 1–3 (`RuntimePolicy`, `SelectionKey`, `weighted_select`),
  injected `domain_eligible` for overlay `auto` resolution.
- Produces:
  - `DispatchDecision(endpoint_id: str, model: str, effort: str,
    table_used: str, excluded_unverified: tuple[str, ...])` (frozen).
  - `select_for_role(policy, role: str, key: SelectionKey, *,
    domain_eligible=None) -> DispatchDecision`
    — resolves overlay tri-state: `enabled`→overlay table; `disabled`→base;
    `auto`→overlay iff `domain_eligible("ox_combo")`; filters UNVERIFIED
    endpoints from the candidate list BEFORE the single deterministic walk
    (spec §13.1 — PLUS_LUNA_XHIGH until registered); survivors renormalize
    through the §6 cumulative walk; raises `POLICY_ENDPOINT_UNVERIFIED` ONLY
    if filtering leaves an empty candidate set; records every filtered
    endpoint in `excluded_unverified`.
  - GrokMode structural guard: any resolved gpt_plus endpoint in grok_mode
    raises `MODE_EXCLUDED_GPT_PLUS` (never reachable with shipped tables;
    guards config regressions).

- [ ] **Step 1: Write failing tests**:
  1. SCOUT sol-mode over 10k synthetic ordinals approximates 70/20/10 (±0.02).
  2. SCOUT never yields GROK/SOL/OPUS endpoints in either mode (10k draws).
  3. STANDARD_WORKER: sol base vs overlay produce different selected sets;
     overlay includes OX_ALPHA at ≈30% (±0.02).
  4. GrokMode STANDARD_WORKER: overlay inactive → §5.5a base ≈70/30, zero OX;
     overlay active → ≈30/55/15; scout/deep grok_mode draws contain zero
     PLUS_LUNA/SOL_HIGH/PLUS_LUNA_XHIGH (10k draws each).
  5. DEEP_WORKER grok-mode ≈67/28/5 (±0.02).
  6. Every returned (model, effort) pair matches policy endpoint_resolution.
  7. Unverified rule (spec §13.1): with PLUS_LUNA_XHIGH marked unverified,
     DEEP_WORKER/sol_mode excludes it BEFORE the walk; empirical shares over
     10k keys renormalize to Grok 60/90≈0.667, Gemini 25/90≈0.278,
     Step 5/90≈0.056 (±0.02); each DispatchDecision carries
     `excluded_unverified=("PLUS_LUNA_XHIGH",)`; a fixture whose survivors are
     all unverified raises POLICY_ENDPOINT_UNVERIFIED.
  8. Determinism: same key → same DispatchDecision.

- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_role_dispatch -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_role_dispatch`.
- [ ] **Step 3: Minimal implementation** — composition layer, no new algorithms (~80 lines).
- [ ] **Step 4: Run tests, verify PASS**
Run: `python3 -m unittest tests.test_runtime_role_dispatch -v` then `python3 -m unittest discover -s tests` (distribution tests ~seconds).
- [ ] **Step 5: Commit**
```bash
git add core/runtime_role_dispatch.py tests/test_runtime_role_dispatch.py
git commit -m "feat(routing): mode-aware Scout/Standard/Deep worker dispatch"
```

### Task 6: OX optional overlay switch + OX agent declaration

**Files:**
- Modify: `core/runtime_routing_policy.py` (add `resolve_overlay`)
- Create: `agents/router-model-nine-router-ox-alpha.toml`
- Modify: `scripts/verify.sh` — three exact locations:
  (a) `ALL_LEAF_AGENTS` array (~line 172): add
    `"router-model-nine-router-ox-alpha.toml"`;
  (b) `expected_agents` map (~line 292): add entry
    `{"kind": "router", "name": "router_nine_router_ox_alpha",
    "model": "nine-router/OX-ALpha"}`;
  (c) dynamic-routing heredoc argv (~line 637–644): append the OX agent path.
- `tests/test_verify.py`: NO agent-list edit required — it is a black-box
  suite driving `verify.sh` as a subprocess and holds no expected-agents
  fixture (its agent constants cover only luna/gemini paths). Coverage comes
  from the clean-room lifecycle check below; optionally add a tamper case
  asserting verify.sh FAILS when the installed OX TOML is corrupted.
- Test: `tests/test_runtime_ox_overlay.py`

**Interfaces:**
- Consumes: policy `ox_overlay` tri-state (Task 2), domain eligibility callable.
- Produces:
  - `resolve_overlay(policy_or_setting, ox_domain_eligible) -> bool`
    (`enabled`→True; `disabled`→False; `auto`→`ox_domain_eligible("ox_combo")`).
  - Managed agent declaration following exactly the pattern of
    `agents/router-model-nine-router-ag-gemini-3-7-flash-high.toml`:
    `name = "router_nine_router_ox_alpha"`,
    `model_provider = "codex-router"`, `model = "nine-router/OX-ALpha"`,
    leaf-isolation developer instructions identical in spirit to sibling
    router agents.
  - NOTE recorded here and in the TOML header comment: adding a file under
    `agents/` changes installer payload discovery (`build_payload` auto-globs
    `agents/*.toml`) AND verify.sh hard-codes its declaration list, so this
    task MUST update the three verify.sh sites and then pass the clean-room
    lifecycle check.
  - Registry gate (spec §11 + §13.1): `PLUS_LUNA_XHIGH` remains unregistered
    until upstream xhigh acceptance is verified; there is NO Luna-Max remap;
    fail-closed behavior is delivered by Task 5's
    `POLICY_ENDPOINT_UNVERIFIED` path.

- [ ] **Step 1: Write failing tests**: resolve_overlay truth table incl.
  cooldown-suppressed auto case; OX TOML exists, parses, name/model match
  spec §11 identity row; updated verify.sh accepts the OX declaration;
  clean-room install/verify/uninstall exits 0 end-to-end with the OX file
  present (9 agents).
- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_ox_overlay -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_routing_policy.resolve_overlay` (or missing attribute).
- [ ] **Step 3: Implementation** — resolve_overlay helper (~20 lines), OX
  TOML, and the three verify.sh edits (no test_verify.py agent-list change;
  see Files note).
- [ ] **Step 4: Verify PASS**
Run: `python3 -m unittest tests.test_runtime_ox_overlay -v`; then clean-room:
`TMP_HOME="$(mktemp -d)"; ./scripts/install.sh --target-home "$TMP_HOME" && ./scripts/verify.sh --target-home "$TMP_HOME" && ./scripts/uninstall.sh --target-home "$TMP_HOME"; rm -rf "$TMP_HOME"` (expect 9 agent declarations, exit 0); then full suite.
- [ ] **Step 5: Commit**
```bash
git add core/runtime_routing_policy.py agents/router-model-nine-router-ox-alpha.toml scripts/verify.sh tests/test_runtime_ox_overlay.py
git commit -m "feat(routing): OX overlay tri-state + managed OX-ALpha agent declaration"
```
Gate: `./scripts/verify.sh --target-home "$TMP_HOME"` exits 0 with 9 agents;
full unittest suite green.

### Task 7: Reviewer independence selector

**Files:**
- Create: `core/runtime_reviewer_selector.py`
- Test: `tests/test_runtime_reviewer_selector.py`

**Interfaces:**
- Consumes: Tasks 2, 3, 8 (health injectable as callable).
- Produces:
  - `ReviewerDecision(selected: str | None, exhausted_reason: str | None,
    pipeline_trace: tuple[tuple[str, str], ...])` (frozen; trace records stage
    name + outcome per candidate).
  - `select_reviewer(policy, implementer_endpoint: str, mode: RoutingMode,
    key: SelectionKey, *, domain_eligible=None) -> ReviewerDecision`
    implementing exactly five ordered stages, in this order:
    1. candidate construction;
    2. implementer INDEPENDENCE-GROUP exclusion via ONE explicit endpoint→
       group map in the policy: every GPT-family endpoint — SOL_HIGH,
       PLUS_LUNA, PLUS_LUNA_XHIGH, OCG_LUNA, and any future
       `nine-router/cx/gpt-5.6-*` route — maps to the single group
       `"gpt_family"` (one label per endpoint, no overlapping families). A
       candidate sharing ANY group with the implementer is excluded: a Sol
       implementer can never be reviewed by any Luna variant incl. OCG_LUNA,
       and an OCG_LUNA implementer can never be reviewed by Sol or Plus
       Lunas. Group membership is data in `runtime-routing.yaml`, extensible
       without code change;
    3. mode eligibility — drop gpt_plus candidates in grok_mode;
    4. health eligibility — `domain_eligible(capacity_domain)` per candidate
       (capacity-domain membership drives ONLY health filtering here, never
       an earlier reviewer-exclusion stage);
    5. weighted selection over survivors using the reviewer_tables row.
    This matches spec §5.8's mandated order exactly; pipeline_trace records
    each candidate's outcome at each stage number.
  - Exhaustion → `selected=None`, `exhausted_reason="REVIEWER_CHAIN_EXHAUSTED"`;
    the API exposes NO fallback-to-implementer path.

- [ ] **Step 1: Write failing tests** (one per spec §5.8 row + structural):
  1. Implementer SOL_HIGH → survivors {GROK,GEMINI,OPUS} @65/25/10; trace
     proves PLUS_LUNA absent at every stage.
  2. Implementer PLUS_LUNA → same survivor row (same `gpt_family` group
     excludes Sol AND Luna xhigh AND itself).
  2b. Independence groups (bidirectional): implementer SOL_HIGH → OCG_LUNA
     excluded by the group stage despite different failure domain;
     implementer OCG_LUNA → SOL_HIGH and PLUS_LUNA both excluded; trace
     records reason `INDEPENDENCE_GROUP` for each exclusion.
  3. Grok implementer, sol_mode → Gemini 60 / Opus 20 / Luna 20.
  4. Grok implementer, grok_mode → Gemini 75 / Opus 25 (no Luna).
  5. Gemini implementer, sol_mode → Grok 60 / Luna 25 / Opus 15.
  6. Gemini implementer, grok_mode → Grok 75 / Opus 25.
  7. STEP implementer → Grok 60 / Gemini 30 / Opus 10; OX implementer → same.
  8. All survivors unhealthy → REVIEWER_CHAIN_EXHAUSTED, selected None.
  9. Cross-check with existing validator:
     `PolicyValidator.validate_verifier_independence` semantics hold for every
     produced pair on a fixture registry (self-conflict + family conflict).
  10. Determinism: same key → same decision; distribution of row 1 over 10k
      keys within ±0.02.
  11. Stage-ORDER enforcement: for implementer SOL_HIGH with gpt_plus in
      cooldown, pipeline_trace shows OCG_LUNA removed at stage 2
      (independence group) with reason INDEPENDENCE_GROUP, never reaching
      stage 4; a candidate removed at an earlier stage MUST NOT appear as
      removed at any later stage; trace stage numbers are strictly
      non-decreasing per candidate. Proves the mandated five-stage order is
      enforced structurally, not incidental.
- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_reviewer_selector -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_reviewer_selector`.
- [ ] **Step 3: Minimal implementation** (~90 lines; reuses weighted_select).
- [ ] **Step 4: Run tests, verify PASS**
Run: `python3 -m unittest tests.test_runtime_reviewer_selector -v` then `python3 -m unittest discover -s tests`.
- [ ] **Step 5: Commit**
```bash
git add core/runtime_reviewer_selector.py tests/test_runtime_reviewer_selector.py
git commit -m "feat(routing): five-stage implementer-independent reviewer selection"
```
Gate: tests 1–2 prove the Sol-implementer-never-reviewed-by-Luna invariant.

### Task 8: Failure domains + health/cooldown

**Files:**
- Create: `core/runtime_routing_health.py`
- Test: `tests/test_runtime_routing_health.py`

**Interfaces:**
- Consumes: `FailureDomain` declarations (Task 2).
- Produces:
  - `DomainHealth` enum: `ELIGIBLE`, `COOLDOWN`.
  - `HEALTH_STATE_PATH_DEFAULT = ~/.agents/runtime-routing/health.json`.
  - `record_quota_exhaustion(domain: str, now_utc: datetime,
    cooldown: timedelta = timedelta(minutes=30), path=...) -> None`
    — sets COOLDOWN(until=now+cooldown) for THAT domain only.
  - `record_transient_error(domain: str, path=...) -> None` — MUST NOT change
    eligibility state (telemetry hook; enforced by test).
  - `domain_eligible(domain: str, now_utc: datetime | None = None, path=...)
    -> bool` — expired cooldown lazily restores ELIGIBLE and prunes the file;
    corrupt/missing file → all eligible (+ anomaly sidecar).
  - `clear_health(path=...) -> None` (operator reset).
  - Hard invariant: this module never imports or writes mode state — a test
    greps the module source for forbidden tokens (`write_mode`, `RoutingMode`)
    and fails if found.

- [ ] **Step 1: Failing tests**: quota exhaustion on gpt_plus makes
  `domain_eligible("gpt_plus")` False while gemini stays True; transient
  error leaves ELIGIBLE; expired cooldown restores True without touching mode
  file; corrupt health JSON → eligible + anomaly; clear_health resets;
  source-grep invariant passes.
- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_routing_health -v`
Expected: FAIL — `ModuleNotFoundError: core.runtime_routing_health`.
- [ ] **Step 3: Minimal implementation** (atomic JSON, lazy expiry, ~100 lines).
- [ ] **Step 4: Run tests, verify PASS**
Run: `python3 -m unittest tests.test_runtime_routing_health -v` then `python3 -m unittest discover -s tests`.
- [ ] **Step 5: Commit**
```bash
git add core/runtime_routing_health.py tests/test_runtime_routing_health.py
git commit -m "feat(routing): failure-domain health and cooldown state"
```

### Task 9: Routing telemetry + target-share report + Controller CLI

**Files:**
- Create: `core/runtime_routing_telemetry.py`
- Create: `scripts/route_model.py`
- Test: `tests/test_runtime_routing_telemetry.py`

**Interfaces:**
- Consumes: Tasks 1, 2, 3, 5, 7, 8 (all composable/injectable).
- Produces:
  - `RoutingEvent` dataclass (fields mirror spec §8 exactly): timestamp_utc,
    mode, role, endpoint_id, endpoint_independence_group, capacity_domain,
    implementer_independence_group (verifier rows only),
    excluded_unverified: tuple[str, ...] (populated when §13.1 filtering
    applied), mission_id, ordinal, overlay_used: bool, latency_class,
    outcome_class.
  - `append_event(event, path=~/.agents/runtime-routing/routing-telemetry.jsonl)
    -> None` — single-line JSON append; identifiers sanitized via
    `core.model_availability.sanitize_identifier`.
  - `aggregate(path, window: timedelta | None = None) -> TargetShareReport`
    — observed per-pool share vs `global_targets`, delta-only output.
  - CLI `scripts/route_model.py`:
    `select --role ROLE [--mission-id M] [--ordinal N] [--state-path P]
    [--health-path H]` — read-only selection print (JSON:
    endpoint/model/effort/table); uses live persisted mode + health; NO
    mutating subcommand exists.
    `report [--window-hours N]` — prints target-share table.

- [ ] **Step 1: Failing tests**: append→aggregate round-trip on temp path;
  secret-looking strings sanitized; window filter excludes old events; report
  deltas match hand-computed fixture (e.g. 45/25/17/7/6 targets vs synthetic
  counts); `select --role scout` under a temp state file forced to grok_mode
  never returns a gpt_plus endpoint across 200 invocations with varying
  ordinals; `--help` exits 0; grep-guard: selection modules never import the
  telemetry module.
- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_runtime_routing_telemetry -v`
Expected: FAIL — import error for telemetry module / missing CLI.
- [ ] **Step 3: Minimal implementation** (append-only writer + aggregator +
  thin argparse CLI).
- [ ] **Step 4: Run tests, verify PASS**
Run: `python3 -m unittest tests.test_runtime_routing_telemetry -v`; CLI smoke: `python3 scripts/route_model.py select --role scout --state-path "$(mktemp -d)/m.json" | python3 -m json.tool`; then `python3 -m unittest discover -s tests`.
- [ ] **Step 5: Commit**
```bash
git add core/runtime_routing_telemetry.py scripts/route_model.py tests/test_runtime_routing_telemetry.py
git commit -m "feat(routing): append-only telemetry, target-share report, read-only select CLI"
```

### Task 10: SolMode/GrokMode user-facing trigger documentation (shadow posture)

**Files:**
- Modify: `skills/sol-luna-orchestrator-v2/SKILL.md` — APPEND a
  "Mode-Aware Routing (Shadow)" section: documents persisted mode, trigger
  phrases, and states that legacy binding remains authoritative until
  activation gate; existing binding section byte-identical.
- Modify: `skills/grok-orchestrator-v2/SKILL.md` — same treatment.
- Modify: `skills/*/USAGE.md` — document
  `orchestrator_mode.py status|set` and trigger phrases
  ("Use SolMode …", "Use GrokMode …").
- Test: `tests/test_verify_mode_docs.py` (NEW; do not edit `test_verify.py`).

**Interfaces:**
- Consumes: CLI surface (Task 1), binding semantics (Task 4).
- Produces: documented user-facing triggers mapping to mode-set + skill
  invocation during transition; compatibility statement preserved.

- [ ] **Step 1: Failing doc test**: both SKILL.mds contain the exact heading
  `## Mode-Aware Routing (Shadow)` and the sentence binding authority to
  legacy until activation; both USAGE.mds contain `orchestrator_mode.py` and
  both trigger phrases.
- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_verify_mode_docs -v`
Expected: FAIL — shadow-mode heading not present in SKILL.mds yet.
- [ ] **Step 3: Edits** — append-only inside skills; zero modifications to
  existing lines (verify via `git diff` showing only additions).
- [ ] **Step 4: Verify PASS**
Run: `python3 -m unittest tests.test_verify_mode_docs -v`; then clean-room:
`TMP_HOME="$(mktemp -d)"; ./scripts/install.sh --target-home "$TMP_HOME" && ./scripts/verify.sh --target-home "$TMP_HOME" && ./scripts/uninstall.sh --target-home "$TMP_HOME"; rm -rf "$TMP_HOME"` (payload hashes change; verify.sh must still exit 0); then `python3 -m unittest discover -s tests`.
- [ ] **Step 5: Commit**
```bash
git add skills/ tests/test_verify_mode_docs.py
git commit -m "docs(skills): document SolMode/GrokMode triggers and shadow posture"
```

### Task 11: Shadow-vs-legacy acceptance evidence

**Files:**
- Create: `tests/test_shadow_acceptance.py`
- Create: `scripts/shadow_report.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - Corpus test: 500 synthetic missions × both modes × roles:
    (a) sol_mode with all-eligible domains → Boss decision SOL_HIGH for every
    mission (matches legacy binding);
    (b) grok_mode → GROK_4_6_HIGH always;
    (c) zero gpt_plus endpoints in ANY grok_mode decision;
    (d) every (implementer, reviewer) pair passes domain independence and
    `PolicyValidator.validate_verifier_independence` on a Core-derived
    fixture registry;
    (e) reviewer exhaustion surfaces as REVIEWER_CHAIN_EXHAUSTED, never as
    self-review.
  - `scripts/shadow_report.py`: emits human-readable acceptance summary;
    test asserts its summary lines contain the five verdicts above.

- [ ] **Step 1: Write failing acceptance tests** (`tests/test_shadow_acceptance.py`): the five verdict classes from Interfaces, each initially failing because `shadow_report.py` does not exist.
- [ ] **Step 2: Run tests, verify FAIL**
Run: `python3 -m unittest tests.test_shadow_acceptance -v`
Expected: FAIL — module/script missing.
- [ ] **Step 3: Implement** `scripts/shadow_report.py` (fixture-driven comparison printout) until all five verdicts pass.
- [ ] **Step 4: Verify PASS**
Run: `python3 -m unittest tests.test_shadow_acceptance -v && python3 scripts/shadow_report.py`; then `python3 -m unittest discover -s tests`; then clean-room:
`TMP_HOME="$(mktemp -d)"; ./scripts/install.sh --target-home "$TMP_HOME" && ./scripts/verify.sh --target-home "$TMP_HOME" && ./scripts/uninstall.sh --target-home "$TMP_HOME"; rm -rf "$TMP_HOME"`.
- [ ] Step 5: Commit
```bash
git add tests/test_shadow_acceptance.py scripts/shadow_report.py
git commit -m "test(routing): shadow-vs-legacy acceptance evidence"
```
Gate: THIS evidence requires operator review BEFORE Task 12 proceeds.

### Task 12: Live activation + rollback verification (explicitly gated)

**Precondition:** Operator approval of Task 11 evidence. Executes the
activation design fixed in spec §2.4 and §12.

**Files:**
- Modify: `core/ORCHESTRATOR_CORE.md` — registry additions
  `STEP_3_7_FLASH`, `OX_ALPHA` (and `PLUS_LUNA_XHIGH` ONLY after upstream
  verification per spec §11/§13.1); new section cross-referencing runtime
  routing; verifier-chain note for domain-level independence.
- Modify: `skills/sol-luna-orchestrator-v2/SKILL.md`,
  `skills/grok-orchestrator-v2/SKILL.md` — binding sections switch to
  mode-checked chains; pre-activation binding text preserved verbatim in the
  rollback appendix of the new CORE section.
- Modify: `scripts/installer_lifecycle.py` PAYLOAD — managed publication of
  runtime-routing modules, CLIs, and `config/runtime-routing.yaml`.
- Modify: `scripts/verify.sh` — dynamic checks: runtime-routing YAML validates;
  mode file (if present) contains a legal value; boss chains match CORE;
  grok_mode tables contain zero gpt_plus endpoints; cx routes absent.
- Tests: extend `tests/test_verify.py` fixtures for registry additions;
  new assertions for the checks above; update
  `tests/test_installer_lifecycle.py` payload expectations.

**Rollback design (implemented and tested in this task):** reverting the two
SKILL.md binding sections to their quoted pre-activation text restores legacy
behavior with no other changes required; `verify.sh` gains a
`--check-rollback-compat` mode asserting the quoted legacy text still matches
the CORE boss bindings, so rollback compatibility cannot rot silently.

- [ ] **Step 1: Write failing tests first** (per touched subsystem, in order):
  (a) registry fixtures: extend `tests/test_policy_validator.py` with
  `STEP_3_7_FLASH` / `OX_ALPHA` registry entries.
     Run: `python3 -m unittest tests.test_policy_validator -v`
     Expected: FAIL — unknown endpoint.
  (b) verify.sh checks: extend `tests/test_verify.py` black-box cases that
     corrupt the installed `runtime-routing.yaml` / mode file inside a temp
     home; verify.sh must reject them.
     Run: `python3 -m unittest tests.test_verify.VerifyBlackBoxTests -v`
     Expected: FAIL — new cases fail because verify.sh has no checks yet.
  (c) rollback-compat: add
     `VerifyBlackBoxTests.test_check_rollback_compat_flag` asserting
     `verify.sh --check-rollback-compat` exits 0 against a legacy-text fixture
     home.
     Run: `python3 -m unittest tests.test_verify.VerifyBlackBoxTests.test_check_rollback_compat_flag -v`
     Expected: FAIL — flag not implemented yet.
- [ ] **Step 2: Implement in separate commits**:
  CORE registry edit → skills binding flip → installer PAYLOAD extension →
  verify.sh dynamic checks. After each: run its task test command.
- [ ] **Step 3: Full verification**
Run: `python3 -m unittest discover -s tests`; then clean-room:
`TMP_HOME="$(mktemp -d)"; ./scripts/install.sh --target-home "$TMP_HOME" && ./scripts/verify.sh --target-home "$TMP_HOME" && ./scripts/uninstall.sh --target-home "$TMP_HOME"; rm -rf "$TMP_HOME"`; then `TMP_HOME="$(mktemp -d)"; ./scripts/install.sh --target-home "$TMP_HOME" && ./scripts/verify.sh --target-home "$TMP_HOME" --check-rollback-compat; rm -rf "$TMP_HOME"`.
- [ ] **Step 4: Operator gate (non-code)**: present Task 11 evidence + this
  task's verification output to the operator; activation commits proceed ONLY
  on explicit operator sign-off recorded in the final commit body. If the
  operator declines, STOP — Tasks 1–11 remain mergeable without activation.

Commit sequence (executed during Step 2, one commit per subsystem, each after
its subsystem test passes):

```bash
git add core/ORCHESTRATOR_CORE.md tests/test_policy_validator.py
git commit -m "feat(core): register STEP_3_7_FLASH and OX_ALPHA routing endpoints"
git add skills/sol-luna-orchestrator-v2/SKILL.md skills/grok-orchestrator-v2/SKILL.md
git commit -m "feat(skills): activate mode-checked Boss bindings"
git add scripts/installer_lifecycle.py tests/test_installer_lifecycle.py config/runtime-routing.yaml
git commit -m "feat(installer): manage runtime-routing payload"
git add scripts/verify.sh tests/test_verify.py
git commit -m "feat(verify): dynamic runtime-routing and rollback-compat validation"
```
- [ ] **Step 5: Final gate** — full suite green; clean-room
  install/verify/uninstall green; operator sign-off recorded in the final
  commit body. Deployment to live `~/.agents` remains a SEPARATE
  post-promotion action per AGENTS.md promotion flow (develop → main → install).

---

## Plan Self-Review Record

1. **Spec coverage:** modes/state+CLI (T1); policy schema, tables, domains,
   targets, tri-state (T2); pinned selector (T3); Boss shadow integration
   (T4); Scout/Standard/Deep policies (T5); OX overlay + missing OX
   declaration (T6); reviewer pipeline incl. all six rows (T7); failure
   domains + health (T8); telemetry + report (T9); user-facing triggers
   (T10); shadow-first acceptance (T11); activation + rollback (T12);
   advisory-resolver non-touch and models.yaml immutability carried by Global
   Constraints. Luna-xhigh fail-closed rule (spec §13.1) implemented in T5
   step 7 test and gated out of T12 registry edits. No gaps.
2. **Placeholder scan:** no TBD/TODO/"later". Every task names files, exact
   test/verification commands, and expected outcomes; test cases enumerate
   concrete assertions and tolerances; code bodies included where they pin
   contracts. Clean-room commands are spelled out at every use site.
3. **Type consistency:** `SelectionKey(mode, mission_id, role, ordinal)`
   identical in T3/T5/T7/T9; `CandidateWeight` defined T2, consumed T3/T5/T7;
   `domain_eligible: Callable[[str], bool]` signature consistent T4–T9;
   `independence_groups` (group→endpoints) + `group_of()` defined T2,
   consumed by T7's stage 2; reviewer tables keyed by independence group in
   T2/T7; `RoutingMode` values stable from T1; `POLICY_ENDPOINT_UNVERIFIED`
   and `REVIEWER_CHAIN_EXHAUSTED` spelled identically everywhere.
4. **Post-review amendments:** GrokMode worker base §5.5a added; Luna-xhigh
   pre-selection exclusion rule; Task 6 verify.sh three-site update with
   test_verify.py clarified as no-edit; Task 7 pipeline reordered to the
   mandated five stages with independence-group exclusion at stage 2 and
   bidirectional OCG_LUNA tests; stage-order enforcement test added.
