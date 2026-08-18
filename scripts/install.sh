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

get_sha256() {
  local file="$1"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${file}" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${file}" | awk '{print $1}'
  else
    python3 -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" "${file}"
  fi
}

# Temporary manifest tracking file during install
TEMP_MANIFEST="$(mktemp)"
echo "{" > "${TEMP_MANIFEST}"
echo '  "version": 1,' >> "${TEMP_MANIFEST}"
echo '  "installed_files": {' >> "${TEMP_MANIFEST}"

FIRST_ENTRY=1

install_tracked_file() {
  local src="$1"
  local dest="$2"
  local dest_dir
  dest_dir="$(dirname "${dest}")"
  local backup_path=""

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] Would install: ${src} -> ${dest}"
    return 0
  fi

  mkdir -p "${dest_dir}"

  if [[ -f "${dest}" ]]; then
    backup_path="${dest}.pre-orchestrator-backup.$(date +%s)"
    echo "Backing up pre-existing file: ${dest} -> ${backup_path}"
    cp -p "${dest}" "${backup_path}"
  fi

  cp -p "${src}" "${dest}"
  local installed_sha
  installed_sha="$(get_sha256 "${dest}")"
  echo "Installed: ${dest}"

  if [[ "${FIRST_ENTRY}" -eq 0 ]]; then
    echo "," >> "${TEMP_MANIFEST}"
  fi
  FIRST_ENTRY=0

  # Write JSON entry
  echo -n "    \"${dest}\": {\"installed_sha256\": \"${installed_sha}\", \"backup_path\": \"${backup_path}\"}" >> "${TEMP_MANIFEST}"
}

# 1. Install Shared Core
install_tracked_file "${REPO_ROOT}/core/ORCHESTRATOR_CORE.md" "${SHARED_DIR}/ORCHESTRATOR_CORE.md"

# 2. Install Skills
install_tracked_file "${REPO_ROOT}/skills/sol-luna-orchestrator-v2/SKILL.md" "${SKILLS_DIR}/sol-luna-orchestrator-v2/SKILL.md"
install_tracked_file "${REPO_ROOT}/skills/sol-luna-orchestrator-v2/USAGE.md" "${SKILLS_DIR}/sol-luna-orchestrator-v2/USAGE.md"
install_tracked_file "${REPO_ROOT}/skills/sol-luna-orchestrator-v2/agents/openai.yaml" "${SKILLS_DIR}/sol-luna-orchestrator-v2/agents/openai.yaml"

install_tracked_file "${REPO_ROOT}/skills/grok-orchestrator-v2/SKILL.md" "${SKILLS_DIR}/grok-orchestrator-v2/SKILL.md"
install_tracked_file "${REPO_ROOT}/skills/grok-orchestrator-v2/USAGE.md" "${SKILLS_DIR}/grok-orchestrator-v2/USAGE.md"
install_tracked_file "${REPO_ROOT}/skills/grok-orchestrator-v2/agents/openai.yaml" "${SKILLS_DIR}/grok-orchestrator-v2/agents/openai.yaml"

# 3. Install Agent Definitions
for agent_file in "${REPO_ROOT}/agents/"*.toml; do
  if [[ -f "${agent_file}" ]]; then
    filename="$(basename "${agent_file}")"
    install_tracked_file "${agent_file}" "${CODEX_AGENTS_DIR}/${filename}"
  fi
done

# Close JSON manifest
echo "" >> "${TEMP_MANIFEST}"
echo '  }' >> "${TEMP_MANIFEST}"
echo "}" >> "${TEMP_MANIFEST}"

if [[ "${DRY_RUN}" -eq 0 ]]; then
  mkdir -p "$(dirname "${MANIFEST_FILE}")"
  mv "${TEMP_MANIFEST}" "${MANIFEST_FILE}"
else
  rm -f "${TEMP_MANIFEST}"
fi

# 4. Install Config Profiles (only if absent)
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
