#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Safe Uninstaller
# Thin wrapper: ownership/hash checks, backup restore, and mutation planning are
# centralized in installer_lifecycle.py.

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
MANIFEST_FILE="${TARGET_HOME}/.agents/.multi-orchestrator-install-manifest.json"
LIFECYCLE_HELPER="${SCRIPT_DIR}/installer_lifecycle.py"

echo "=== Multi Orchestrator Safe Uninstallation ==="
echo "Target Root: ${TARGET_HOME}"

remove_dir_if_empty() {
  local dir="$1"
  if [[ -d "${dir}" ]]; then
    rmdir "${dir}" 2>/dev/null && echo "Removed empty directory: ${dir}" || true
  fi
}

if ! python3 "${LIFECYCLE_HELPER}" uninstall --target-home "${TARGET_HOME}" --manifest-path "${MANIFEST_FILE}"; then
  echo "[ERROR] Uninstallation aborted." >&2
  exit 1
fi

# Clean empty directories left behind by removed payload files.
remove_dir_if_empty "${TARGET_HOME}/.agents/orchestrator-shared"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/agents"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/agents"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2"
remove_dir_if_empty "${TARGET_HOME}/.agents/bin"
remove_dir_if_empty "${TARGET_HOME}/.codex/agents"

echo ""
echo "=== Uninstallation Completed Successfully ==="
echo "Note: Configuration profiles (.codex/*.config.toml) were left untouched."
