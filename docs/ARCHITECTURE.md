# Multi Orchestrator — Architecture Specification

## 1. Overview
Multi Orchestrator is an engine-agnostic multi-agent orchestration architecture designed for local execution runtimes (such as OpenAI Codex CLI). It establishes a deterministic, safe, and observable framework for delegating complex software engineering workflows across specialized AI model agents.

---

## 2. System Topology
The architecture strictly operates as a centralized **Hub-and-Spoke** topology:

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

### Delegation Invariants
- **Leaf Subagent Invariant (`TOPOLOGY_HUB_AND_SPOKE_ONLY`):** All workers and verifiers are leaf subagents. Subagents cannot spawn child agents, cannot delegate to peer agents, and cannot establish nested delegation chains.
- **Parent Override Blocked:** A prompt from a parent instructing a subagent to spawn additional workers is structurally prohibited by the subagent contract.
- **Central Integration:** All results, findings, and patches return exclusively to the Parent Boss for synthesis and validation.

---

## 3. Component Hierarchy & Layering
1. **Canonical Shared Core (`ORCHESTRATOR_CORE.md`):**
   - Single source of truth for routing chains, packet schemas, verification skip logic, failure handling, and mission health.
2. **Thin Parent Wrappers (`sol-luna-orchestrator-v2`, `grok-orchestrator-v2`):**
   - Environment and profile bindings for specific parent models (e.g. `gpt-5.6-sol` or `grok-4.6-high`).
   - Pure consumers of the Shared Core; no local policy deviations.
3. **Execution Subagents:**
   - Provider-qualified leaf models declared via `.codex/agents/*.toml`.

---

## 4. Context & Task Isolation
- **`fork_turns="none"`:** Subagents never inherit parent conversation history. This guarantees zero prompt pollution, predictable token consumption, and strict isolation.
- **Explicit Packet Contracts:** All assignments are communicated via standardized YAML/JSON packets:
  - `WORKER_TASK_PACKET`: 15 mandatory fields defining objective, boundaries, owned files, forbidden paths, and validation checks.
  - `VERIFICATION_PACKET`: 13 mandatory fields guaranteeing independent verification criteria without implementer reasoning bias.
  - `prior_attempt_summary`: 10 mandatory fields driving structured rework cycles.
- **Zero Chain-of-Thought Leakage:** Packets communicate strictly through factual decisions, citations, and error logs—never private reasoning traces.

---

## 5. Development Workspace Topology vs. Runtime
- **Source Control Topology:** Managed as two Git worktrees: `stable/` (`main`) for audited baselines and `dev/` (`develop`) for all active development.
- **Runtime Environment:** Deployed separately into `~/.agents` and `~/.codex` via `scripts/install.sh`. Development work never targets the active runtime directly.
