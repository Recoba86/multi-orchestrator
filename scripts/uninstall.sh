#!/usr/bin/env bash
set -euo pipefail

# Orchestrator V2 Uninstaller
# Removes files installed by the Orchestrator V2 package without affecting unrelated skill or agent configurations.

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

echo "=== Orchestrator V2 Uninstallation ==="
echo "Target Root: ${TARGET_HOME}"

remove_file() {
  local target="$1"
  if [[ -f "${target}" ]]; then
    rm -f "${target}"
    echo "Removed: ${target}"
  fi
}

remove_dir_if_empty() {
  local dir="$1"
  if [[ -d "${dir}" ]]; then
    rmdir "${dir}" 2>/dev/null && echo "Removed empty directory: ${dir}" || true
  fi
}

# 1. Remove Shared Core
remove_file "${TARGET_HOME}/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md"
remove_dir_if_empty "${TARGET_HOME}/.agents/orchestrator-shared"

# 2. Remove Skills
remove_file "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/SKILL.md"
remove_file "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/USAGE.md"
remove_file "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/agents/openai.yaml"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/agents"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2"

remove_file "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/SKILL.md"
remove_file "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/USAGE.md"
remove_file "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/agents/openai.yaml"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/agents"
remove_dir_if_empty "${TARGET_HOME}/.agents/skills/grok-orchestrator-v2"

# 3. Remove Agent Definitions
for agent_file in "${REPO_ROOT}/agents/"*.toml; do
  if [[ -f "${agent_file}" ]]; then
    filename="$(basename "${agent_file}")"
    remove_file "${TARGET_HOME}/.codex/agents/${filename}"
  fi
done

echo ""
echo "=== Uninstallation Completed ==="
echo "Note: Configuration profiles (.codex/*.config.toml) were left untouched to protect custom settings."
