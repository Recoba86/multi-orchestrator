#!/usr/bin/env bash
set -euo pipefail

# Orchestrator V2 Static Verifier
# Validates presence, syntax, and critical safety contracts across the installed Orchestrator V2 environment.

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

FAILED=0
assert_file_exists() {
  local file="$1"
  if [[ ! -f "${file}" ]]; then
    echo "[FAIL] Missing file: ${file}" >&2
    FAILED=1
  else
    echo "[PASS] Found file: ${file}"
  fi
}

assert_contains() {
  local file="$1"
  local pattern="$2"
  local desc="$3"
  if ! grep -qF "${pattern}" "${file}" 2>/dev/null; then
    echo "[FAIL] ${desc} (Missing '${pattern}' in ${file})" >&2
    FAILED=1
  else
    echo "[PASS] ${desc}"
  fi
}

assert_not_contains() {
  local file="$1"
  local pattern="$2"
  local desc="$3"
  if grep -qF "${pattern}" "${file}" 2>/dev/null; then
    echo "[FAIL] ${desc} (Unexpected '${pattern}' in ${file})" >&2
    FAILED=1
  else
    echo "[PASS] ${desc}"
  fi
}

echo "=== Orchestrator V2 Verification ==="
echo "Target Root: ${TARGET_HOME}"
echo ""

CORE="${TARGET_HOME}/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md"
SOL_SKILL="${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/SKILL.md"
GROK_SKILL="${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/SKILL.md"
OPUS_AGENT="${TARGET_HOME}/.codex/agents/router-model-nine-router-ag-claude-opus-4-6-thinking.toml"
LUNA_AGENT="${TARGET_HOME}/.codex/agents/luna_max_worker.toml"

# 1. Existence Checks
assert_file_exists "${CORE}"
assert_file_exists "${SOL_SKILL}"
assert_file_exists "${GROK_SKILL}"
assert_file_exists "${OPUS_AGENT}"
assert_file_exists "${LUNA_AGENT}"

# 2. Topology Checks
assert_contains "${CORE}" "TOPOLOGY_HUB_AND_SPOKE_ONLY" "Core defines Hub-and-Spoke topology"
assert_contains "${CORE}" "Worker-to-Worker Delegation Forbidden" "Core forbids worker delegation"
assert_contains "${CORE}" "Subagent Spawning Forbidden" "Core forbids subagent spawning"
assert_contains "${LUNA_AGENT}" "You are a leaf subagent in a strict Hub-and-Spoke topology." "Luna agent is explicit leaf"
assert_not_contains "${LUNA_AGENT}" "unless the parent explicitly instructs" "Luna agent has no conditional spawn escape hatch"
assert_contains "${OPUS_AGENT}" "Do not spawn, delegate to, or orchestrate additional agents or subagents." "Opus agent has absolute no-spawn"

# 3. Opus Isolation Checks
assert_contains "${CORE}" "role: PREMIUM_SECOND_OPINION" "Opus registered as PREMIUM_SECOND_OPINION"
assert_contains "${CORE}" "access: READ_ONLY" "Opus access is READ_ONLY"
assert_contains "${CORE}" "write_ownership: NONE" "Opus write ownership is NONE"
assert_contains "${OPUS_AGENT}" "You are a read-only independent reviewer" "Opus agent prompt is read-only"

# 4. Context & Packet Isolation
assert_contains "${CORE}" "fork_turns=\"none\"" "Core enforces fork_turns='none'"
assert_contains "${CORE}" "WORKER_TASK_PACKET:" "Worker task packet schema defined"
assert_contains "${CORE}" "VERIFICATION_PACKET:" "Verification packet schema defined"
assert_contains "${CORE}" "prior_attempt_summary:" "Rework schema defined"
assert_contains "${CORE}" "PACKET_INVALID" "Packet invalidity rule defined"

# 5. Verification Invariant & Exhaustion
assert_contains "${CORE}" "IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK" "Core enforces verifier != implementer"
assert_contains "${CORE}" "VERIFIER_CHAIN_EXHAUSTED" "Core defines verifier chain exhaustion"

# 6. Mutation Safety
assert_contains "${CORE}" "AMBIGUOUS_EXECUTION_STATE" "Core defines ambiguous write state"

echo ""
if [[ "${FAILED}" -ne 0 ]]; then
  echo "=== VERIFICATION FAILED ===" >&2
  exit 1
else
  echo "=== ALL VERIFICATION CHECKS PASSED ==="
  exit 0
fi
