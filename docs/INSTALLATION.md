# Orchestrator V2 — Installation & Configuration Guide

## 1. Quick Installation

Run the automated installer from the root of this repository:

```bash
./scripts/install.sh
```

### Dry Run
To inspect files that would be installed without making any modifications:

```bash
./scripts/install.sh --dry-run
```

---

## 2. Target Filesystem Layout
The installer places runtime files in your home directory:

```text
~/.agents/
├── orchestrator-shared/
│   └── ORCHESTRATOR_CORE.md       # Normative Policy & Packet Schemas
└── skills/
    ├── sol-luna-orchestrator-v2/  # Sol Parent Wrapper
    └── grok-orchestrator-v2/      # Grok Parent Wrapper

~/.codex/
├── agents/                        # Subagent Declarations (*.toml)
├── sol-luna.config.toml           # Sol Profile Configuration
└── grok-v2.config.toml            # Grok Profile Configuration
```

---

## 3. Post-Installation Verification
Validate that all files and safety invariants are correctly installed:

```bash
./scripts/verify.sh
```

---

## 4. Usage in Codex CLI

### Sol Boss (Default)
```bash
codex --profile sol-luna
```
Prompt:
```text
Use $sol-luna-orchestrator-v2 to plan and execute this feature with multi-role subagents.
```

### Grok Boss (Alternative)
```bash
codex --profile grok-v2
```
Prompt:
```text
Use $grok-orchestrator-v2 to plan and execute this feature with multi-role subagents.
```

---

## 5. Uninstallation
To cleanly remove installed orchestrator components without affecting custom configs:

```bash
./scripts/uninstall.sh
```
