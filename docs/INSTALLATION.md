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
│   └── models.yaml                # Unmanaged canonical operator policy
├── core/                          # Managed Model Policy & Resolver Modules
├── orchestrator-shared/
│   └── ORCHESTRATOR_CORE.md       # Normative Policy & Packet Schemas
└── skills/
    └── autoteam/                  # Canonical Auto Team wrapper

~/.codex/
├── agents/                        # Subagent Declarations (*.toml)
├── sol-luna.config.toml           # Sol Profile Configuration
└── grok-v2.config.toml            # Grok Profile Configuration
```

The installer seeds `~/.agents/config/models.yaml` as an unmanaged, user-owned
configuration file. Its `operator_policy` is the canonical model/effort
selection for all six Auto Team roles; the four logical-role views are
advisory projections and are preserved across upgrades and uninstalls.

---

## 3. Post-Installation Verification
Validate that all files and safety invariants are correctly installed:

```bash
./scripts/verify.sh
```

---

## 4. Usage in Codex CLI

### Auto Team Skill (Default)
```bash
codex --profile sol-luna
```
Prompt:
```text
Use $autoteam to plan and execute this feature with multi-role subagents.
```

The persistent `SolMode` and `GrokMode` controls are compatibility and
observability state. With runtime routing enabled, both use the same canonical
Auto Team model chains; they do not silently replace the operator policy.

### Legacy rollback profiles
```bash
codex --profile grok-v2
```
Prompt:
```text
Use the legacy Grok profile only when explicitly rolling back runtime routing.
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

## 7. Explicit Manifest v1 → v2 Migration

Older installs with a `version: 1` manifest are intentionally rejected by ordinary `install`, `verify`, and `uninstall` commands. Run the migration explicitly against a disposable or approved target home:

```bash
./scripts/install.sh --migrate-manifest-v1 --target-home "$TARGET_HOME"
```

Add `--dry-run` to print the complete classification plan without creating directories, copying, replacing, removing, changing modes, or rewriting the manifest. The plan validates every legacy path and SHA-256 before mutation. Each relevant path is classified once as `pristine`, `repaired_missing`, `new_payload`, or `preserved_customized`.

Customized legacy agent declarations (`.codex/agents/*.toml`) are preserved byte-for-byte as unmanaged files and recorded in `migration_omissions`; they undergo comprehensive TOML syntax validation during verification, while upstream leaf-agent safety policy assertions apply to managed declarations. A modified Core, skill, command, model-policy module, or other indispensable payload blocks migration before mutation. Unknown, escaping, symlinked, reserved, hash-conflicting, or ambiguous paths also fail closed.

Proven v1 backups are retained or relocated under the confined `.multi-orchestrator-backups/` root and referenced by the v2 manifest. Migration writes the v2 manifest atomically and rolls repository-controlled mutations and the exact v1 manifest back on a controlled failure. Existing models/config files and unrelated files remain untouched; if one of the three unmanaged config files is absent, migration seeds it from the repository after managed migration succeeds. All three repository sources are preflighted before any managed migration mutation.

After migration, normal upgrades never reclaim preserved declarations. Uninstall removes only clean v2-owned files and restores validated backups; preserved customized declarations and user configuration remain in place. Re-run `verify.sh --target-home "$TARGET_HOME"` after migration to inspect both managed payload hashes and preserved declarations.

## 8. Optional Model-Role Configuration

Edit `config/models.yaml` (or installed `~/.agents/config/models.yaml`) when documenting local model choices.
Its `preferred` and `fallback` lists preserve user order from first to last as optional recommendations.

### Commands
- **Doctor (`python3 scripts/doctor.py` or installed `~/.agents/bin/doctor`):**
  Performs read-only validation of `models.yaml`, discovers local Codex declarations, analyzes capability compatibility, reports offline availability observations, joins offline intelligence profiles, and runs deterministic advisory role resolutions (`resolve_role`). Does not probe remote providers, mutate files, or interact with the Host.
- **Model Configuration (`python3 scripts/configure_models.py` or installed `~/.agents/bin/configure-models`):**
  Inspects or safely updates role preferences. Default mode is dry-run. Mutating configuration requires explicit `--apply`, `--approve`, and `--expected-sha256 <SHA>` flags, performing byte-exact backups and atomic file writes.

See the [Doctor guide](ORCHESTRATOR_DOCTOR.md) and [model configuration contract](MODEL_CONFIGURATION.md).
