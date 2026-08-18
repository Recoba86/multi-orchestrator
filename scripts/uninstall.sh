#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Safe Uninstaller
# Restores pre-existing files, preserves user-modified files, and cleans up installed package files.

TARGET_HOME="${HOME}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-home)
      TARGET_HOME="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--target-home <dir>]" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MANIFEST_FILE="${TARGET_HOME}/.agents/.multi-orchestrator-install-manifest.json"

echo "=== Multi Orchestrator Safe Uninstallation ==="
echo "Target Root: ${TARGET_HOME}"

remove_dir_if_empty() {
  local dir="$1"
  if [[ -d "${dir}" ]]; then
    rmdir "${dir}" 2>/dev/null && echo "Removed empty directory: ${dir}" || true
  fi
}

if [[ -f "${MANIFEST_FILE}" ]]; then
  echo "Found install manifest: ${MANIFEST_FILE}"
  
  python3 -c '
import json, os, sys, hashlib

manifest_path = sys.argv[1]
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest = json.load(f)

installed_files = manifest.get("installed_files", {})

def get_file_sha256(path):
    if not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()

for path, info in installed_files.items():
    if not os.path.exists(path):
        continue
    
    expected_sha = info.get("installed_sha256")
    backup_path = info.get("backup_path")
    current_sha = get_file_sha256(path)
    
    # Check if user modified the file after install
    if current_sha != expected_sha:
        b_info = backup_path if backup_path else "None"
        print(f"[WARN] User modified file detected: {path}")
        print(f"       Preserving modified file. Backup located at: {b_info}")
        continue
    
    # File is unmodified by user
    if backup_path and os.path.exists(backup_path):
        # Restore original pre-existing file byte-for-byte
        os.replace(backup_path, path)
        print(f"[RESTORED] Pre-existing file restored: {path} (from {backup_path})")
    else:
        # No backup existed prior to install, safe to remove
        os.remove(path)
        print(f"[REMOVED] Cleanly removed package file: {path}")
' "${MANIFEST_FILE}"

  rm -f "${MANIFEST_FILE}"
  echo "Removed manifest file."

else
  echo "No manifest found, executing legacy fallback removal..."
  remove_file() {
    local target="$1"
    if [[ -f "${target}" ]]; then
      rm -f "${target}"
      echo "Removed: ${target}"
    fi
  }

  remove_file "${TARGET_HOME}/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md"
  remove_file "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/SKILL.md"
  remove_file "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/USAGE.md"
  remove_file "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/agents/openai.yaml"
  remove_file "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/SKILL.md"
  remove_file "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/USAGE.md"
  remove_file "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/agents/openai.yaml"

  for agent_file in "${REPO_ROOT}/agents/"*.toml; do
    if [[ -f "${agent_file}" ]]; then
      filename="$(basename "${agent_file}")"
      remove_file "${TARGET_HOME}/.codex/agents/${filename}"
    fi
  done
fi

# Clean empty directories
remove_dir_if_empty "${TARGET_HOME}/.agents/orchestrator-shared"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/agents"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/agents"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2"
remove_dir_if_empty "${TARGET_HOME}/.codex/agents"

echo ""
echo "=== Uninstallation Completed ==="
echo "Note: Configuration profiles (.codex/*.config.toml) were left untouched."
