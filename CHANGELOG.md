# Changelog

All notable changes to the Orchestrator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
