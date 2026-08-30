# Changelog

All notable changes to the Orchestrator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-08-30

### Added
- **Mode-Aware Weighted Runtime Routing (SolMode / GrokMode):**
  - Persistent manual mode state storage (`~/.agents/runtime-routing/mode.json`) and CLI (`orchestrator-mode status|SolMode|GrokMode`).
  - Master activation switch (`orchestrator-routing on|off|status`) with immediate legacy rollback kill-switch.
  - Pure deterministic weighted model selection algorithm based on single SHA-256 cumulative bucket.
  - Failure-domain health cooldown tracking with automatic TTL expiration.
  - Append-only routing telemetry and target-share aggregate report generator.
  - Declarative runtime routing configuration in `config/runtime-routing.yaml`.
  - Extended test suite with 407 passing unit and integration tests.

## [1.2.2] - 2026-08-25

### Added
- **Provider-Agnostic Model Policy Framework & RC4 Release:**
  - Declarative role configuration via `config/models.yaml` for planner, scout, worker, and reviewer roles.
  - Read-only doctor diagnostic tool (`scripts/doctor.py`) and safe configuration CLI (`scripts/configure-models.py`).
  - Atomic manifest v1 to v2 installer migration with ownership tracking and backup capabilities.

## [1.2.1] - 2026-08-19

### Added
- **Canonical Mission Identity (`MISSION_IDENTITY`):** Immutable bindings for `mission_id`, `workspace_root`, `git_toplevel`, `repository_identity`, `starting_branch`, `starting_sha`, and `boss_child_id`.
- **Workspace Preflight & Fail-Closed Invariants:** Controller preflight protocol verifying `workspace_root == git_toplevel` (`TARGET_WORKSPACE_MISMATCH`) and strict packet identity matching (`MISSION_CONTEXT_MISMATCH`).
- **Executable Pure Identity Validator:** Shipped `core/identity_validator.py` with comprehensive unit and negative test suite in `tests/test_isolation_identity.py`.
- **Mission Trace V2 Workspace Identity:** Extended trace schema and CLI renderer to durably record repository identity, git toplevel match, and per-action identity validation status.

### Changed
- **Skill Metadata Cleanup:** Removed stale leaf-routing instructions from `sol-luna-orchestrator-v2/agents/openai.yaml` and corrected SKILL frontmatter descriptions to reflect Dedicated Boss architecture rather than parent-session constraints.
- **Documentation Alignment:** Updated `README.md`, `docs/ARCHITECTURE.md`, and `docs/INSTALLATION.md` to ensure complete consistency with RC3 Dedicated Boss topologies.
- **Gitignore Restoration:** Restored standard OS, temporary, backup, and editor ignore patterns in `.gitignore`.

## [1.2.0] - 2026-08-19

### Added
- **Dedicated Boss Architecture (RC3):** Formal separation between Control Plane (Root Controller), Decision Plane (Dedicated Skill-Bound Boss), and Execution Plane (Workers/Verifiers).
- **Skill-to-Boss Binding:** Strict binding mapping `grok-orchestrator-v2` to `GROK_4_6_HIGH` and `sol-luna-orchestrator-v2` to `SOL_HIGH`.
- **Dedicated Boss Continuity:** Enforced same-child Boss persistence via child follow-up tasks across multi-turn missions.
- **Fail-Closed Controller Invariants:** Root Controller cannot self-promote to Boss if Boss binding fails; invalid actions or substitution attacks fail closed.
- **Mission Trace Subsystem:** Structured JSON logging in `~/.codex/orchestrator-traces/<mission_id>.json` with CLI tool `mission-trace` and automatic secret redaction.
- **Automated Invariant Test Suite:** Added `tests/test_invariants.py` covering positive and negative policy invariants.

### Changed
- **Wrapper Definitions:** Updated `grok-orchestrator-v2` and `sol-luna-orchestrator-v2` skills to define the Root Controller protocol and dedicated Boss spawning requirements.
- **Installer / Uninstaller Lifecycle:** Added `mission-trace` executable to managed installed files under `~/.agents/bin/mission-trace`.

## [1.1.0] - 2026-08-19

### Added
- **Dynamic Policy Verification:** Upgraded `scripts/verify.sh` to dynamically validate routing structure, endpoint registries, accepted efforts, policy caps, implementer self-conflicts, and model-family independence directly from `ORCHESTRATOR_CORE.md`.

## [1.0.0] - 2026-08-19

### Added
- Initial release candidate for Multi Orchestrator Core and Skills.
