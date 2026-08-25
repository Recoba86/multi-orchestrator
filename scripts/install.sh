#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Installer
# Thin wrapper: manifest validation, ownership checks, backup metadata, and
# mutation planning are centralized in installer_lifecycle.py.

DRY_RUN=0
MIGRATE_MANIFEST_V1=0
TARGET_HOME="${HOME}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --migrate-manifest-v1)
      MIGRATE_MANIFEST_V1=1
      shift
      ;;
    --target-home)
      TARGET_HOME="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--dry-run] [--migrate-manifest-v1] [--target-home <dir>]" >&2
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

# Install Unmanaged Config Files (only if absent); these examples and the
# user-owned models config are intentionally not part of the ownership
# manifest, so upgrade/uninstall never overwrites or removes them.
install_unmanaged_file() {
  local src="$1"
  local dest="$2"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    echo "[DRY-RUN] Would copy unmanaged file (if absent): ${src} -> ${dest}"
    return 0
  fi
  mkdir -p "$(dirname "${dest}")"
  if [[ ! -f "${dest}" ]]; then
    cp -p "${src}" "${dest}"
    echo "Created unmanaged file: ${dest}"
  else
    echo "Unmanaged file exists, preserving: ${dest}"
  fi
}

if [[ "${MIGRATE_MANIFEST_V1}" -eq 1 ]]; then
  echo "Mode: EXPLICIT MANIFEST v1 -> v2 MIGRATION"
  missing_sources=0
  for source in \
    "${REPO_ROOT}/config/sol-luna.config.example.toml" \
    "${REPO_ROOT}/config/grok-v2.config.example.toml" \
    "${REPO_ROOT}/config/models.yaml"; do
    if [[ ! -f "${source}" ]]; then
      echo "[ERROR] Missing unmanaged config source: ${source}" >&2
      missing_sources=1
    fi
  done
  if [[ "${missing_sources}" -ne 0 ]]; then
    echo "[ERROR] Manifest migration aborted before mutation." >&2
    exit 1
  fi
  HELPER_ARGS=(migrate-manifest-v1 --repo-root "${REPO_ROOT}" --target-home "${TARGET_HOME}" --manifest-path "${MANIFEST_FILE}")
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    HELPER_ARGS+=(--dry-run)
  fi
  if ! python3 "${LIFECYCLE_HELPER}" "${HELPER_ARGS[@]}"; then
    echo "[ERROR] Manifest migration aborted." >&2
    exit 1
  fi
  install_unmanaged_file "${REPO_ROOT}/config/sol-luna.config.example.toml" "${CODEX_DIR}/sol-luna.config.toml"
  install_unmanaged_file "${REPO_ROOT}/config/grok-v2.config.example.toml" "${CODEX_DIR}/grok-v2.config.toml"
  install_unmanaged_file "${REPO_ROOT}/config/models.yaml" "${TARGET_HOME}/.agents/config/models.yaml"
  echo "Manifest migration and payload reconciliation completed."
  exit 0
fi

HELPER_ARGS=(install --repo-root "${REPO_ROOT}" --target-home "${TARGET_HOME}" --manifest-path "${MANIFEST_FILE}")
if [[ "${DRY_RUN}" -eq 1 ]]; then
  HELPER_ARGS+=(--dry-run)
fi

if ! python3 "${LIFECYCLE_HELPER}" "${HELPER_ARGS[@]}"; then
  echo "[ERROR] Installation aborted." >&2
  exit 1
fi

install_unmanaged_file "${REPO_ROOT}/config/sol-luna.config.example.toml" "${CODEX_DIR}/sol-luna.config.toml"
install_unmanaged_file "${REPO_ROOT}/config/grok-v2.config.example.toml" "${CODEX_DIR}/grok-v2.config.toml"
install_unmanaged_file "${REPO_ROOT}/config/models.yaml" "${TARGET_HOME}/.agents/config/models.yaml"

echo ""
echo "=== Installation Completed Successfully ==="
echo "Manifest saved: ${MANIFEST_FILE}"
echo "To verify installation, run: scripts/verify.sh [--target-home <dir>]"
