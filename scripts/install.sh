#!/usr/bin/env bash
set -euo pipefail

# Orchestrator V2 Installer
# Installs Shared Core, Skills, Agent Definitions, and Configuration Examples to the user's HOME environment.

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

echo "=== Orchestrator V2 Installation ==="
echo "Target Root: ${TARGET_HOME}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Mode: DRY RUN (no modifications will be made)"
fi

install_file() {
  local src="$1"
  local dest="$2"
  local dest_dir
  dest_dir="$(dirname "${dest}")"

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] Would install: ${src} -> ${dest}"
    return 0
  fi

  mkdir -p "${dest_dir}"

  if [[ -f "${dest}" ]]; then
    local backup="${dest}.backup.$(date +%s)"
    echo "Backing up existing ${dest} -> ${backup}"
    cp -p "${dest}" "${backup}"
  fi

  cp -p "${src}" "${dest}"
  echo "Installed: ${dest}"
}

# 1. Install Shared Core
install_file "${REPO_ROOT}/core/ORCHESTRATOR_CORE.md" "${SHARED_DIR}/ORCHESTRATOR_CORE.md"

# 2. Install Skills
install_file "${REPO_ROOT}/skills/sol-luna-orchestrator-v2/SKILL.md" "${SKILLS_DIR}/sol-luna-orchestrator-v2/SKILL.md"
install_file "${REPO_ROOT}/skills/sol-luna-orchestrator-v2/USAGE.md" "${SKILLS_DIR}/sol-luna-orchestrator-v2/USAGE.md"
install_file "${REPO_ROOT}/skills/sol-luna-orchestrator-v2/agents/openai.yaml" "${SKILLS_DIR}/sol-luna-orchestrator-v2/agents/openai.yaml"

install_file "${REPO_ROOT}/skills/grok-orchestrator-v2/SKILL.md" "${SKILLS_DIR}/grok-orchestrator-v2/SKILL.md"
install_file "${REPO_ROOT}/skills/grok-orchestrator-v2/USAGE.md" "${SKILLS_DIR}/grok-orchestrator-v2/USAGE.md"
install_file "${REPO_ROOT}/skills/grok-orchestrator-v2/agents/openai.yaml" "${SKILLS_DIR}/grok-orchestrator-v2/agents/openai.yaml"

# 3. Install Agent Definitions
for agent_file in "${REPO_ROOT}/agents/"*.toml; do
  if [[ -f "${agent_file}" ]]; then
    filename="$(basename "${agent_file}")"
    install_file "${agent_file}" "${CODEX_AGENTS_DIR}/${filename}"
  fi
done

# 4. Install Config Profiles (only if not already present)
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
echo "Shared Core: ${SHARED_DIR}/ORCHESTRATOR_CORE.md"
echo "Skills Directory: ${SKILLS_DIR}"
echo "Codex Agents Directory: ${CODEX_AGENTS_DIR}"
echo "To verify installation, run: scripts/verify.sh [--target-home <dir>]"
