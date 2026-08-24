# Multi Orchestrator

A deterministic, multi-agent orchestration architecture for OpenAI Codex and CLI workflows.

Multi Orchestrator coordinates specialized AI model subagents across complex software engineering tasks using centralized planning, strict Hub-and-Spoke isolation, implementer-aware independent verification, and fail-closed safety contracts.

---

## Key Features

- **Strict Hub-and-Spoke Protocol:** Controller-submitted requests assign subagents as leaf nodes and prohibit nested delegation or peer chatter.
- **Requested Context Isolation (`fork_turns="none"`):** Controller-submitted requests use self-contained task packets without inherited turns.
- **Implementer-Aware Independent Verification:** The agent that implements code cannot verify it (`verifier != implementer`). If verifiers are exhausted, tasks remain unverified rather than self-approved.
- **Fail-Closed Mutation Safety:** Ambiguous write state makes the Controller refuse further write-capable requests.
- **Dedicated Read-Only Premium Review:** High-stakes review requests assign Claude Opus 4.6 Thinking a read-only, non-mutating contract.
- **Deterministic 3-Attempt Fallback:** Predictable request-routing chains across Scout, Standard Worker, and Deep Worker roles.

These are repository protocol guarantees. Native child allocation, effective identity, and Host-wide admission are `HOST_EXTERNAL`; this repository does not intercept or authorize them. See the authoritative [Execution Boundary Model](core/ORCHESTRATOR_CORE.md#execution-boundary-model-host_external--authoritative).

---

## Architecture at a Glance

```text
      User / Developer
             │
             ▼
       ROOT_CONTROLLER
 (Session Model / Control Plane)
             │
             ▼ (submits Host requests & relays)
      DEDICATED_BOSS
  (Skill-Bound: Sol High / Grok High)
             │ (decisions / actions)
             ▼
       ROOT_CONTROLLER
             │ (protocol-validated Host requests)
   ┌─────────┼─────────┬──────────────────────┬───────────────────────┐
   ▼         ▼         ▼                      ▼                       ▼
 Scout    Standard    Deep     Implementer-Aware   Premium        Dedicated Boss
(Read)     Worker    Worker         Verifier       Reviewer        (Decision Plane)
(gemini)  (gemini)   (dseek)     (!implementer)    (Opus)         (Sol / Grok)
   │         │         │              │               │               ▲
   └─────────┼─────────┴──────────────┴───────────────┴───────────────┘
             │ (Structured Factual Execution Results)
             ▼
       ROOT_CONTROLLER
             │ (lossless relay via follow-up)
             │
             └────────────────────────────────────────────────────────┘
             │
             ▼
      User / Developer
```

---

## Quick Start

### 1. Install
```bash
git clone https://github.com/Recoba86/multi-orchestrator.git
cd multi-orchestrator
./scripts/install.sh
```

### 2. Verify
```bash
./scripts/verify.sh
```

### 3. Run with Codex CLI
```bash
# Launch with Sol Parent
codex --profile sol-luna

# In chat:
Use $sol-luna-orchestrator-v2 to plan and execute this feature with multi-role subagents.
```

---

## Documentation

- [Architecture Specification](docs/ARCHITECTURE.md)
- [Safety Invariants & Failure Taxonomy](docs/SAFETY.md)
- [Model Registry & Routing](docs/MODELS.md)
- [Installation Guide](docs/INSTALLATION.md)

---


---

## Development & Governance

For this private repository, work is organized into two permanent Git worktrees:
- **`stable/` (`main`):** Known-good, audited release baseline. Direct development is prohibited.
- **`dev/` (`develop`):** Normal development workspace where all new features, bug fixes, and refactors begin.

For detailed developer and agent instructions, see:
- [Agent Instructions & Preflight Guardrails](AGENTS.md)
- [Development Workflow Guide](docs/DEVELOPMENT_WORKFLOW.md)
- [Promotion & Release Process](docs/RELEASE_PROCESS.md)
- [Self-Development Safety Guide](docs/SELF_DEVELOPMENT.md)
- [Current Project State](docs/PROJECT_STATE.md)

## License & Security

- **Security:** Please see [SECURITY.md](SECURITY.md) for vulnerability reporting.
- **License:** MIT. See [LICENSE](LICENSE).
