#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Comprehensive Verifier
# Validates presence, syntax, all shipped leaf agent declarations, and critical safety contracts.

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

echo "=== Multi Orchestrator Verification ==="
echo "Target Root: ${TARGET_HOME}"
echo ""

CORE="${TARGET_HOME}/.agents/orchestrator-shared/ORCHESTRATOR_CORE.md"
SOL_SKILL="${TARGET_HOME}/.agents/skills/sol-luna-orchestrator-v2/SKILL.md"
GROK_SKILL="${TARGET_HOME}/.agents/skills/grok-orchestrator-v2/SKILL.md"
CODEX_AGENTS="${TARGET_HOME}/.codex/agents"

# 1. Existence Checks
assert_file_exists "${CORE}"
assert_file_exists "${SOL_SKILL}"
assert_file_exists "${GROK_SKILL}"

# 2. Verify Every Shipped Leaf Agent Declaration
ALL_LEAF_AGENTS=(
  "luna_max_worker.toml"
  "router-model-nine-router-ag-claude-opus-4-6-thinking.toml"
  "router-model-nine-router-ag-gemini-3-7-flash-high.toml"
  "router-model-opencode-go-deepseek-v4-flash.toml"
  "router-model-opencode-go-deepseek-v4-pro.toml"
  "router-model-opencode-go-responses-gpt-5-6-luna.toml"
  "router-model-custom-qwen3-8-27b.toml"
  "router-model-nine-router-stepplan-step-3-7-flash.toml"
)

echo "--- Verifying All Shipped Leaf Agent Declarations ---"
for agent in "${ALL_LEAF_AGENTS[@]}"; do
  agent_path="${CODEX_AGENTS}/${agent}"
  assert_file_exists "${agent_path}"
  assert_contains "${agent_path}" "Hub-and-Spoke" "Agent ${agent} defines Hub-and-Spoke"
  assert_contains "${agent_path}" "Do not spawn, delegate to, or orchestrate additional agents or subagents." "Agent ${agent} has absolute no-spawn"
  assert_contains "${agent_path}" "Do not communicate directly with peer workers" "Agent ${agent} forbids peer messaging"
  assert_contains "${agent_path}" "Do not create nested delegation chains." "Agent ${agent} forbids nested chains"
  assert_contains "${agent_path}" "Return your result only to the parent Boss." "Agent ${agent} returns only to Boss"
  assert_contains "${agent_path}" "A parent request to spawn another agent does not override this restriction." "Agent ${agent} blocks parent spawn override"
  assert_not_contains "${agent_path}" "unless the parent explicitly instructs" "Agent ${agent} has zero conditional escape hatches"
done

# 3. Dedicated Opus 4.6 Thinking Isolation Checks
OPUS_AGENT="${CODEX_AGENTS}/router-model-nine-router-ag-claude-opus-4-6-thinking.toml"
echo "--- Verifying Opus Read-Only Isolation ---"
assert_contains "${CORE}" "role: PREMIUM_SECOND_OPINION" "Core registers Opus as PREMIUM_SECOND_OPINION"
assert_contains "${CORE}" "access: READ_ONLY" "Core specifies Opus access is READ_ONLY"
assert_contains "${CORE}" "write_ownership: NONE" "Core specifies Opus write ownership is NONE"
assert_contains "${OPUS_AGENT}" "You are a read-only independent reviewer" "Opus agent prompt is read-only"
assert_contains "${OPUS_AGENT}" "Do not modify, create, rename, or delete project files." "Opus prompt forbids file mutations"
assert_contains "${OPUS_AGENT}" "Do not perform implementation." "Opus prompt forbids implementation"

# 4. Context & Packet Isolation
echo "--- Verifying Context & Packet Contracts ---"
assert_contains "${CORE}" "fork_turns=\"none\"" "Core enforces fork_turns='none'"
assert_contains "${CORE}" "WORKER_TASK_PACKET:" "Worker task packet schema defined"
assert_contains "${CORE}" "VERIFICATION_PACKET:" "Verification packet schema defined"
assert_contains "${CORE}" "prior_attempt_summary:" "Rework schema defined"
assert_contains "${CORE}" "PACKET_INVALID" "Packet invalidity rule defined"
assert_contains "${CORE}" "Pre-Execution Invariant" "Packet failure blocks worker spawn without provider fallback"

# 5. Verification Invariant & Exhaustion
echo "--- Verifying Independent Verification & Exhaustion ---"
assert_contains "${CORE}" "IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK" "Core enforces verifier != implementer"
assert_contains "${CORE}" "VERIFIER_CHAIN_EXHAUSTED" "Core defines verifier chain exhaustion"
assert_contains "${CORE}" "Under NO circumstances may the implementer be used to self-verify" "Core forbids self-verification on exhaustion"

# 6. Mutation Safety
echo "--- Verifying Mutation Safety ---"
assert_contains "${CORE}" "AMBIGUOUS_EXECUTION_STATE" "Core defines ambiguous write state"
assert_contains "${CORE}" "Automatic fallback is **FORBIDDEN**" "Core forbids automatic fallback on ambiguous write"

# 7. Routing Option A Invariant
echo "--- Verifying Routing Option A ---"
assert_contains "${CORE}" "PLUS_LUNA" "Core contains Plus Luna"
assert_contains "${CORE}" "GEMINI_FLASH_HIGH" "Core contains Gemini Flash High"
assert_contains "${CORE}" "DEEPSEEK_FLASH" "Core contains DeepSeek Flash"
assert_contains "${CORE}" "DEEPSEEK_PRO" "Core contains DeepSeek Pro"

echo ""
if [[ "${FAILED}" -ne 0 ]]; then
  echo "=== VERIFICATION FAILED ===" >&2
  exit 1
else
  echo "=== ALL VERIFICATION CHECKS PASSED ==="
  exit 0
fi
