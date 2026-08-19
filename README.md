# Multi Orchestrator

A deterministic, multi-agent orchestration architecture for OpenAI Codex and CLI workflows.

Multi Orchestrator coordinates specialized AI model subagents across complex software engineering tasks using centralized planning, strict Hub-and-Spoke isolation, implementer-aware independent verification, and fail-closed safety contracts.

---

## Key Features

- **Strict Hub-and-Spoke Topology:** Subagents operate as pure leaf nodes. Subagent spawning, nested delegation, and peer chatter are prohibited.
- **Total Context Isolation (`fork_turns="none"`):** Subagents execute with zero parent conversation history, receiving 100% self-contained task packets.
- **Implementer-Aware Independent Verification:** The agent that implements code cannot verify it (`verifier != implementer`). If verifiers are exhausted, tasks remain unverified rather than self-approved.
- **Fail-Closed Mutation Safety:** Ambiguous execution states on write-capable workers block further mutations.
- **Dedicated Read-Only Premium Review:** High-stakes architectural and security evaluations use Claude Opus 4.6 Thinking in a strictly read-only, non-mutating capacity.
- **Deterministic 3-Attempt Fallback:** Predictable routing chains across Scout, Standard Worker, and Deep Worker roles.

---

## Architecture at a Glance

```text
               User / Developer
                      │
                      ▼
                 Parent Boss
         (Sol High / Grok 4.6 High)
                      │
   ┌──────────────────┼──────────────────┬──────────────────┐
   ▼                  ▼                  ▼                  ▼
 Scout         Standard Worker      Deep Worker    Independent Verifier
(Read-Only)      (Write-Owned)      (Max-Depth)     (!= Implementer)
(Gemini Flash)   (Gemini Flash)    (DeepSeek Pro)     (Deterministic)
   │                  │                  │                  │
   └──────────────────┼──────────────────┴──────────────────┘
                      │ (Structured Artifacts & Reports)
                      ▼
                 Parent Boss
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
