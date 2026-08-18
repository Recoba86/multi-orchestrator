# Changelog

All notable changes to the Orchestrator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
