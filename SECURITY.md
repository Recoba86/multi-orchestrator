# Security Policy

## Reporting Security Vulnerabilities
If you discover a potential security vulnerability or safety invariant bypass in Multi Orchestrator, please report it privately.

Please do not open public issues for sensitive vulnerabilities.

## Safety Guarantees
These are repository protocol guarantees enforced while the Controller validates and submits requests; native Host allocation, dispatch, and effective identity remain `HOST_EXTERNAL`:
1. **No Self-Verification:** The Controller rejects a verification packet whose verifier matches the implementer.
2. **Strict Disjoint Ownership:** The Controller submits write packets only with explicit, disjoint owned paths.
3. **Ambiguous Write Guard:** The Controller refuses secondary write requests after an uncertain mid-turn state.
4. **Opus Read-Only Invariant:** The Controller's premium-review packet specifies `READ_ONLY`, `write_ownership: NONE`, and no mutating operation.
