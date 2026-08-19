# Changelog

All notable changes to the Orchestrator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-08-19

### Added
- **Dynamic Policy Verification:** Upgraded `scripts/verify.sh` to dynamically validate routing structure, endpoint registries, accepted efforts, policy caps, implementer self-conflicts, and model-family conflicts directly against `ORCHESTRATOR_CORE.md` without static route hardcoding.
- **Luna Model-Family Invariant:** Enforced cross-endpoint model family verification conflict preventing `PLUS_LUNA` and `OCG_LUNA` from verifying each other's work.
- **Authoritative Verifier Chains:** Machine-readable `verifier_chains` defined in `ORCHESTRATOR_CORE.md`.

### Changed
- **Standard Worker Rebalance:** Rebalanced `STANDARD_WORKER` primary attempt to `GEMINI_FLASH_HIGH` (high effort), followed by `PLUS_LUNA` (max effort) as strong fallback, and `DEEPSEEK_FLASH` (high effort) as third attempt.
- **Gemini Verification Routing:** Established dedicated verifier routing for Gemini implementations (`PLUS_LUNA` max ->
ightarrow-> `OCG_LUNA` high), reserving `DEEPSEEK_PRO` primarily for deep work.

---

## [1.0.0] - 2026-08-19

### Added
- **Canonical Release:** Initial public release of Multi Orchestrator architecture.
- **Dual Parent Boss Profiles:** Support for Native Sol Boss (`gpt-5.6-sol`) and Alternate Grok Boss (`grok-4.6-high`).
- **Deterministic Role Chains:** 3-attempt fallback chains for `SCOUT`, `STANDARD_WORKER`, and `DEEP_WORKER`.
- **Implementer-Aware Verification:** Strict enforcement that implementers never verify their own work, with explicit `VERIFIER_CHAIN_EXHAUSTED` handling.
- **Normative Packet Schemas:** Standardized `WORKER_TASK_PACKET` v1, `VERIFICATION_PACKET` v1, and `prior_attempt_summary`.
- **Strict Hub-and-Spoke Topology:** Enforced leaf node constraints on all worker and reviewer agent declarations.
- **Premium Second Opinion:** Dedicated `OPUS_4_6_THINKING` read-only reviewer contract.
- **Fail-Closed Mutation Safety:** `AMBIGUOUS_EXECUTION_STATE` safety policy preventing secondary write attempts on uncertain failures.
