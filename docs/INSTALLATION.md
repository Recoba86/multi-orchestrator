# Multi Orchestrator — Installation & Configuration Guide

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
├── bin/
│   ├── configure-models           # Model Role Configuration Tool
│   ├── doctor                     # Environment & Resolution Doctor
│   └── mission-trace              # Trace Persistence Tool
├── config/
│   └── models.yaml                # Unmanaged User Model Configuration
├── core/                          # Managed Model Policy & Resolver Modules
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

The installer seeds `~/.agents/config/models.yaml` as an unmanaged, user-owned configuration file for the four logical roles (`planner`, `scout`, `worker`, `reviewer`). It is preserved across upgrades and uninstalls.

---

## 3. Post-Installation Verification
Validate that all files and safety invariants are correctly installed:

```bash
./scripts/verify.sh
```

---

## 4. Usage in Codex CLI

### Sol Orchestrator Skill (Default)
```bash
codex --profile sol-luna
```
Prompt:
```text
Use $sol-luna-orchestrator-v2 to plan and execute this feature with multi-role subagents.
```

### Grok Orchestrator Skill (Alternative)
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

---

## 6. Source Workspace vs. Active Runtime
- `multi-orchestrator/stable` and `multi-orchestrator/dev` are Git source directories.
- `scripts/install.sh` copies and configures runtime files into `~/.agents` and `~/.codex`.
- Routine development changes are implemented in `dev/` and must be tested and promoted to `stable/` before running the installer.

## 7. Optional Model-Role Configuration

Edit `config/models.yaml` (or installed `~/.agents/config/models.yaml`) when documenting local model choices.
Its `preferred` and `fallback` lists preserve user order from first to last as optional recommendations.

### Commands
- **Doctor (`python3 scripts/doctor.py` or installed `~/.agents/bin/doctor`):**
  Performs read-only validation of `models.yaml`, discovers local Codex declarations, analyzes capability compatibility, reports offline availability observations, joins offline intelligence profiles, and runs deterministic advisory role resolutions (`resolve_role`). Does not probe remote providers, mutate files, or interact with the Host.
- **Model Configuration (`python3 scripts/configure_models.py` or installed `~/.agents/bin/configure-models`):**
  Inspects or safely updates role preferences. Default mode is dry-run. Mutating configuration requires explicit `--apply`, `--approve`, and `--expected-sha256 <SHA>` flags, performing byte-exact backups and atomic file writes.

See the [Doctor guide](ORCHESTRATOR_DOCTOR.md) and [model configuration contract](MODEL_CONFIGURATION.md).
