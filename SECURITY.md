# Security Policy

## Reporting Security Vulnerabilities
If you discover a potential security vulnerability or safety invariant bypass in Orchestrator V2, please report it privately.

Please do not open public issues for sensitive vulnerabilities.

## Safety Guarantees
Orchestrator V2 is designed around strict fail-closed safety invariants:
1. **No Self-Verification:** Implementers cannot verify their own pull requests or patches.
2. **Strict Disjoint Ownership:** Parallel workers cannot write outside assigned paths.
3. **Ambiguous Write Guard:** Uncertain mid-turn network drops halt automatic write retries.
4. **Opus Read-Only Invariant:** Premium reviewer cannot mutate files or execute mutating commands.
