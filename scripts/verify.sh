#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Comprehensive Verifier
# Validates presence, syntax, all shipped leaf agent declarations, dynamic routing policy, and critical safety contracts.

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

# 7. Dynamic Routing & Policy Correctness Verification
echo "--- Dynamically Verifying Routing Policy & Safety Invariants ---"
if ! python3 -c '
import sys, re, yaml

core_path = sys.argv[1]
with open(core_path, "r", encoding="utf-8") as f:
    text = f.read()

yaml_blocks = re.findall(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
if not yaml_blocks:
    print("[FAIL] No structured YAML blocks found in Core", file=sys.stderr)
    sys.exit(1)

parsed_data = {}
for block in yaml_blocks:
    try:
        loaded = yaml.safe_load(block)
        if isinstance(loaded, dict):
            parsed_data.update(loaded)
    except Exception as e:
        print(f"[FAIL] YAML parse error in Core: {e}", file=sys.stderr)
        sys.exit(1)

# A. Endpoint Registry Verification
endpoints = parsed_data.get("endpoints")
if not endpoints or not isinstance(endpoints, list):
    print("[FAIL] Endpoints registry missing or invalid", file=sys.stderr)
    sys.exit(1)

endpoint_map = {}
for ep in endpoints:
    ep_id = ep.get("id")
    if not ep_id:
        print("[FAIL] Endpoint missing identifier in registry", file=sys.stderr)
        sys.exit(1)
    if not ep.get("accepted_efforts") or not isinstance(ep.get("accepted_efforts"), list):
        print(f"[FAIL] Endpoint {ep_id} missing accepted_efforts list", file=sys.stderr)
        sys.exit(1)
    endpoint_map[ep_id] = ep

print(f"[PASS] Endpoint Registry validated dynamically ({len(endpoint_map)} endpoints)")

# B. Dynamic Role Chains Verification
role_chains = parsed_data.get("role_chains")
if not role_chains or not isinstance(role_chains, dict):
    print("[FAIL] role_chains missing or invalid in Core", file=sys.stderr)
    sys.exit(1)

required_roles = ["SCOUT", "STANDARD_WORKER", "DEEP_WORKER"]
for role in required_roles:
    chain = role_chains.get(role)
    if not chain or not isinstance(chain, list) or len(chain) == 0:
        print(f"[FAIL] Required role {role} missing or empty", file=sys.stderr)
        sys.exit(1)

    for idx, entry in enumerate(chain):
        expected_att = idx + 1
        att = entry.get("attempt")
        if att != expected_att:
            print(f"[FAIL] Role {role} attempt numbering must start at 1 and be contiguous (got {att}, expected {expected_att})", file=sys.stderr)
            sys.exit(1)

        ep_id = entry.get("endpoint")
        if ep_id not in endpoint_map:
            print(f"[FAIL] Role {role} references unknown endpoint {ep_id}", file=sys.stderr)
            sys.exit(1)

        ep = endpoint_map[ep_id]
        model = entry.get("model")
        if model and ep.get("model") and model != ep.get("model"):
            print(f"[FAIL] Model mismatch for {ep_id} in {role}: expected {ep.get('model')}, got {model}", file=sys.stderr)
            sys.exit(1)

        eff = entry.get("effort")
        if eff not in ep.get("accepted_efforts", []):
            print(f"[FAIL] Effort {eff} for {ep_id} in {role} not in accepted_efforts {ep.get('accepted_efforts')}", file=sys.stderr)
            sys.exit(1)

        policy_max = ep.get("policy_max_effort")
        if policy_max:
            eff_levels = {"low": 1, "medium": 2, "high": 3, "max": 4}
            if eff_levels.get(eff, 0) > eff_levels.get(policy_max, 0):
                print(f"[FAIL] Effort {eff} for {ep_id} in {role} exceeds policy_max_effort {policy_max}", file=sys.stderr)
                sys.exit(1)

print("[PASS] Worker role chains validated dynamically against registry, accepted_efforts, and policy caps")

# C. Dynamic Verifier Chains Verification
verifier_chains = parsed_data.get("verifier_chains")
if not verifier_chains or not isinstance(verifier_chains, dict):
    print("[FAIL] verifier_chains missing or invalid in Core", file=sys.stderr)
    sys.exit(1)

# Ensure every write-capable implementation endpoint in worker chains has a valid verifier chain
write_implementers = set()
for r in ["STANDARD_WORKER", "DEEP_WORKER"]:
    for entry in role_chains.get(r, []):
        write_implementers.add(entry.get("endpoint"))

for imp_id in write_implementers:
    if imp_id not in verifier_chains:
        print(f"[FAIL] Write implementer {imp_id} has no defined verifier chain", file=sys.stderr)
        sys.exit(1)

for imp_id, v_chain in verifier_chains.items():
    if imp_id not in endpoint_map:
        print(f"[FAIL] Verifier chain defined for unknown implementer {imp_id}", file=sys.stderr)
        sys.exit(1)

    imp_ep = endpoint_map[imp_id]
    imp_family = imp_ep.get("family")

    if not v_chain or not isinstance(v_chain, list) or len(v_chain) == 0:
        print(f"[FAIL] Verifier chain for {imp_id} is empty", file=sys.stderr)
        sys.exit(1)

    valid_verifiers_count = 0
    for idx, entry in enumerate(v_chain):
        expected_att = idx + 1
        att = entry.get("attempt")
        if att != expected_att:
            print(f"[FAIL] Verifier chain for {imp_id} attempt numbering must be contiguous starting at 1 (got {att}, expected {expected_att})", file=sys.stderr)
            sys.exit(1)

        v_id = entry.get("endpoint")
        if v_id not in endpoint_map:
            print(f"[FAIL] Verifier chain for {imp_id} references unknown endpoint {v_id}", file=sys.stderr)
            sys.exit(1)

        v_ep = endpoint_map[v_id]

        # Invariant 1: Exact Implementer Self-Conflict
        if v_id == imp_id:
            print(f"[FAIL] Exact self-verification prohibited: {v_id} cannot verify itself", file=sys.stderr)
            sys.exit(1)

        # Invariant 2: Model Family Conflict (e.g. PLUS_LUNA <-> OCG_LUNA)
        v_family = v_ep.get("family")
        if imp_family and v_family and imp_family == v_family:
            print(f"[FAIL] Same model family conflict prohibited: verifier {v_id} and implementer {imp_id} both belong to family {imp_family}", file=sys.stderr)
            sys.exit(1)

        model = entry.get("model")
        if model and v_ep.get("model") and model != v_ep.get("model"):
            print(f"[FAIL] Model mismatch for verifier {v_id}: expected {v_ep.get('model')}, got {model}", file=sys.stderr)
            sys.exit(1)

        eff = entry.get("effort")
        if eff not in v_ep.get("accepted_efforts", []):
            print(f"[FAIL] Effort {eff} for verifier {v_id} not in accepted_efforts {v_ep.get('accepted_efforts')}", file=sys.stderr)
            sys.exit(1)

        policy_max = v_ep.get("policy_max_effort")
        if policy_max:
            eff_levels = {"low": 1, "medium": 2, "high": 3, "max": 4}
            if eff_levels.get(eff, 0) > eff_levels.get(policy_max, 0):
                print(f"[FAIL] Effort {eff} for verifier {v_id} exceeds policy_max_effort {policy_max}", file=sys.stderr)
                sys.exit(1)

        valid_verifiers_count += 1

    if valid_verifiers_count == 0:
        print(f"[FAIL] Implementer {imp_id} has no valid independent verifiers", file=sys.stderr)
        sys.exit(1)

print("[PASS] Verifier chains validated dynamically: self-conflicts and model-family conflicts enforced")
' "${CORE}"; then
  echo "[FAIL] Dynamic Routing verification failed" >&2
  FAILED=1
else
  echo "[PASS] Dynamic Routing & Policy Safety verified"
fi

echo ""
if [[ "${FAILED}" -ne 0 ]]; then
  echo "=== VERIFICATION FAILED ===" >&2
  exit 1
else
  echo "=== ALL VERIFICATION CHECKS PASSED ==="
  exit 0
fi
