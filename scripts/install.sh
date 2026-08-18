#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Installer
# Installs Shared Core, Skills, Agent Definitions, and Configuration Examples with safe backup tracking.

DRY_RUN=0
TARGET_HOME="${HOME}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --target-home)
      TARGET_HOME="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--dry-run] [--target-home <dir>]" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SHARED_DIR="${TARGET_HOME}/.agents/orchestrator-shared"
SKILLS_DIR="${TARGET_HOME}/.agents/skills"
CODEX_AGENTS_DIR="${TARGET_HOME}/.codex/agents"
CODEX_DIR="${TARGET_HOME}/.codex"
MANIFEST_FILE="${TARGET_HOME}/.agents/.multi-orchestrator-install-manifest.json"

echo "=== Multi Orchestrator Installation ==="
echo "Target Root: ${TARGET_HOME}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Mode: DRY RUN (no modifications will be made)"
fi

# Pre-validate existing manifest if present
if [[ -f "${MANIFEST_FILE}" ]]; then
  if ! python3 -c "import json, sys; json.load(open(sys.argv[1]))" "${MANIFEST_FILE}" 2>/dev/null; then
    echo "[ERROR] Existing manifest at ${MANIFEST_FILE} is malformed or corrupt." >&2
    echo "        Installation aborted to prevent overwriting ownership/backup history." >&2
    exit 1
  fi
fi

# Execute Python installer helper for robust atomic tracking and backup preservation
python3 -c '
import sys, os, json, shutil, hashlib, time

dry_run = int(sys.argv[1])
repo_root = sys.argv[2]
target_home = sys.argv[3]
manifest_path = sys.argv[4]

def get_sha256(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

# Load existing manifest if present
existing_manifest = {}
if os.path.exists(manifest_path):
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            existing_manifest = json.load(f).get("installed_files", {})
    except Exception as e:
        print(f"[ERROR] Failed to read existing manifest: {e}", file=sys.stderr)
        sys.exit(1)

# Files to install: (source_rel, dest_full)
files_to_install = [
    (os.path.join(repo_root, "core/ORCHESTRATOR_CORE.md"), os.path.join(target_home, ".agents/orchestrator-shared/ORCHESTRATOR_CORE.md")),
    (os.path.join(repo_root, "skills/sol-luna-orchestrator-v2/SKILL.md"), os.path.join(target_home, ".agents/skills/sol-luna-orchestrator-v2/SKILL.md")),
    (os.path.join(repo_root, "skills/sol-luna-orchestrator-v2/USAGE.md"), os.path.join(target_home, ".agents/skills/sol-luna-orchestrator-v2/USAGE.md")),
    (os.path.join(repo_root, "skills/sol-luna-orchestrator-v2/agents/openai.yaml"), os.path.join(target_home, ".agents/skills/sol-luna-orchestrator-v2/agents/openai.yaml")),
    (os.path.join(repo_root, "skills/grok-orchestrator-v2/SKILL.md"), os.path.join(target_home, ".agents/skills/grok-orchestrator-v2/SKILL.md")),
    (os.path.join(repo_root, "skills/grok-orchestrator-v2/USAGE.md"), os.path.join(target_home, ".agents/skills/grok-orchestrator-v2/USAGE.md")),
    (os.path.join(repo_root, "skills/grok-orchestrator-v2/agents/openai.yaml"), os.path.join(target_home, ".agents/skills/grok-orchestrator-v2/agents/openai.yaml")),
]

agents_dir = os.path.join(repo_root, "agents")
for agent_file in sorted(os.listdir(agents_dir)):
    if agent_file.endswith(".toml"):
        src_path = os.path.join(agents_dir, agent_file)
        dest_path = os.path.join(target_home, ".codex/agents", agent_file)
        files_to_install.append((src_path, dest_path))

new_manifest_installed_files = {}

for src, dest in files_to_install:
    dest_dir = os.path.dirname(dest)
    dest_exists = os.path.exists(dest)
    current_dest_sha = get_sha256(dest) if dest_exists else None
    src_sha = get_sha256(src)

    # Check if file was previously tracked in manifest
    prev_info = existing_manifest.get(dest)
    backup_path = None

    if prev_info:
        # File was previously installed by package
        original_backup = prev_info.get("backup_path")
        prev_installed_sha = prev_info.get("installed_sha256")

        # Invariant: preserve original pre-install backup reference
        backup_path = original_backup

        if current_dest_sha != prev_installed_sha:
            # User modified the installed file! Preserve user modification safely
            user_backup = f"{dest}.user-modified-backup.{int(time.time())}"
            if not dry_run:
                shutil.copy2(dest, user_backup)
            print(f"[WARN] User modification detected on {dest}. Backed up to {user_backup}")
    else:
        # File was NOT previously installed by package. If it exists, it is a pre-existing user file!
        if dest_exists:
            backup_path = f"{dest}.pre-orchestrator-backup.{int(time.time())}"
            # Ensure unique backup filename
            counter = 1
            while os.path.exists(backup_path):
                backup_path = f"{dest}.pre-orchestrator-backup.{int(time.time())}_{counter}"
                counter += 1
            if not dry_run:
                shutil.copy2(dest, backup_path)
            print(f"Backing up pre-existing file: {dest} -> {backup_path}")

    if dry_run:
        print(f"[DRY-RUN] Would install: {src} -> {dest}")
    else:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(src, dest)
        print(f"Installed: {dest}")

    new_manifest_installed_files[dest] = {
        "installed_sha256": src_sha,
        "backup_path": backup_path
    }

if not dry_run:
    # Atomically write manifest
    manifest_data = {
        "version": 1,
        "installed_files": new_manifest_installed_files
    }
    manifest_dir = os.path.dirname(manifest_path)
    os.makedirs(manifest_dir, exist_ok=True)
    temp_manifest_file = f"{manifest_path}.tmp.{os.getpid()}"
    with open(temp_manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    os.replace(temp_manifest_file, manifest_path)
' "${DRY_RUN}" "${REPO_ROOT}" "${TARGET_HOME}" "${MANIFEST_FILE}"

# Install Config Profiles (only if absent)
install_config_example() {
  local src="$1"
  local dest="$2"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] Would copy profile (if absent): ${src} -> ${dest}"
    return 0
  fi
  mkdir -p "$(dirname "${dest}")"
  if [[ ! -f "${dest}" ]]; then
    cp -p "${src}" "${dest}"
    echo "Created config profile: ${dest}"
  else
    echo "Config profile exists, preserving: ${dest}"
  fi
}

install_config_example "${REPO_ROOT}/config/sol-luna.config.example.toml" "${CODEX_DIR}/sol-luna.config.toml"
install_config_example "${REPO_ROOT}/config/grok-v2.config.example.toml" "${CODEX_DIR}/grok-v2.config.toml"

echo ""
echo "=== Installation Completed Successfully ==="
echo "Manifest saved: ${MANIFEST_FILE}"
echo "To verify installation, run: scripts/verify.sh [--target-home <dir>]"
