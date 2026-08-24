#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Installer
# Thin wrapper: manifest validation, ownership checks, backup metadata, and
# mutation planning are centralized in installer_lifecycle.py.

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
CODEX_DIR="${TARGET_HOME}/.codex"
MANIFEST_FILE="${TARGET_HOME}/.agents/.multi-orchestrator-install-manifest.json"
LIFECYCLE_HELPER="${SCRIPT_DIR}/installer_lifecycle.py"

echo "=== Multi Orchestrator Installation ==="
echo "Target Root: ${TARGET_HOME}"
if [[ "${DRY_RUN}" -eq 1 ]]; then
  echo "Mode: DRY RUN (no modifications will be made)"
fi

HELPER_ARGS=(install --repo-root "${REPO_ROOT}" --target-home "${TARGET_HOME}" --manifest-path "${MANIFEST_FILE}")
if [[ "${DRY_RUN}" -eq 1 ]]; then
  HELPER_ARGS+=(--dry-run)
fi

if ! python3 "${LIFECYCLE_HELPER}" "${HELPER_ARGS[@]}"; then
  echo "[ERROR] Installation aborted." >&2
  exit 1
fi

# Install Config Profiles (only if absent); these examples are intentionally
# not part of the ownership manifest.
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
