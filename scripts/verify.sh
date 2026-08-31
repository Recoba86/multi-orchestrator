#!/usr/bin/env bash
set -euo pipefail

# Multi Orchestrator Comprehensive Verifier
# Validates presence, syntax, all shipped leaf agent declarations, dynamic routing policy, dedicated Boss invariants, and critical safety contracts.

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

# Fail closed on any malformed, ambiguous, or escaping manifest before any
# other verification or potential mutation.
if [[ -f "${MANIFEST_FILE}" ]]; then
  if ! python3 "${LIFECYCLE_HELPER}" verify --target-home "${TARGET_HOME}" --manifest-path "${MANIFEST_FILE}"; then
    echo "[FAIL] Installer lifecycle validation failed" >&2
    exit 1
  fi
fi

FAILED=0

is_migration_omission() {
  python3 - "${MANIFEST_FILE}" "${TARGET_HOME}" "$1" <<'PY'
import json
from pathlib import Path
import sys

manifest_path, target_home, candidate = sys.argv[1:4]
try:
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    omissions = data.get("migration_omissions", {})
    target = Path(target_home).resolve()
    rel = str(Path(candidate).resolve().relative_to(target))
    if rel in omissions:
        print("1")
        sys.exit(0)
except Exception:
    pass
print("0")
PY
}

assert_file_exists() {
  local file="$1"
  if [[ ! -f "${file}" ]]; then
    if [[ "$(is_migration_omission "${file}")" == "1" ]]; then
      echo "[SKIP] Explicit migration omission (absent): ${file}"
      return 0
    fi
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
  if [[ "$(is_migration_omission "${file}")" == "1" ]]; then
    echo "[SKIP] Explicit migration omission: ${desc}"
    return 0
  fi
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
  if [[ "$(is_migration_omission "${file}")" == "1" ]]; then
    echo "[SKIP] Explicit migration omission: ${desc}"
    return 0
  fi
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
AUTOTEAM_SKILL="${TARGET_HOME}/.agents/skills/autoteam/SKILL.md"
AUTOTEAM_USAGE="${TARGET_HOME}/.agents/skills/autoteam/USAGE.md"
AUTOTEAM_CONFIG="${TARGET_HOME}/.agents/skills/autoteam/agents/openai.yaml"
CODEX_AGENTS="${TARGET_HOME}/.codex/agents"
SOL_CONFIG="${TARGET_HOME}/.codex/sol-luna.config.toml"
GROK_CONFIG="${TARGET_HOME}/.codex/grok-v2.config.toml"
TRACE_HELPER="${TARGET_HOME}/.agents/bin/mission-trace"
DOCTOR="${TARGET_HOME}/.agents/bin/doctor"
CONFIGURE_MODELS="${TARGET_HOME}/.agents/bin/configure-models"
MODELS_CONFIG="${TARGET_HOME}/.agents/config/models.yaml"
MODEL_POLICY_MODULES=(
  "model_availability"
  "model_capabilities"
  "model_discovery"
  "model_intelligence"
  "model_policy"
  "model_resolver"
)
MODEL_POLICY_MODULES+=( "policy_validator" )
RUNTIME_ROUTING_MODULES=(
  "runtime_routing_mode"
  "runtime_adaptive_scheduler"
  "runtime_routing_policy"
  "runtime_weighted_selector"
  "runtime_boss_binding"
  "runtime_role_dispatch"
  "runtime_reviewer_selector"
  "runtime_routing_health"
  "runtime_routing_telemetry"
  "runtime_routing_switch"
  "runtime_endpoint_validator"
)
ORCHESTRATOR_ROUTING_BIN="${TARGET_HOME}/.agents/bin/orchestrator-routing"
ROUTE_MODEL_BIN="${TARGET_HOME}/.agents/bin/route-model"
ORCHESTRATOR_MODE_BIN="${TARGET_HOME}/.agents/bin/orchestrator-mode"
RUNTIME_ROUTING_CONFIG="${TARGET_HOME}/.agents/config/runtime-routing.yaml"

# 1. Existence Checks
assert_file_exists "${CORE}"
assert_file_exists "${AUTOTEAM_SKILL}"
assert_file_exists "${AUTOTEAM_USAGE}"
assert_file_exists "${AUTOTEAM_CONFIG}"
assert_file_exists "${TRACE_HELPER}"

# 1b. Model Policy Payload & Unmanaged Config Existence Checks
echo "--- Verifying Installed Model Policy Payload ---"
for module in "${MODEL_POLICY_MODULES[@]}"; do
  assert_file_exists "${TARGET_HOME}/.agents/core/${module}.py"
done
assert_file_exists "${DOCTOR}"
assert_file_exists "${CONFIGURE_MODELS}"
assert_file_exists "${MODELS_CONFIG}"

echo "--- Verifying Installed Runtime Routing Payload ---"
for module in "${RUNTIME_ROUTING_MODULES[@]}"; do
  assert_file_exists "${TARGET_HOME}/.agents/core/${module}.py"
done
assert_file_exists "${ORCHESTRATOR_ROUTING_BIN}"
assert_file_exists "${ROUTE_MODEL_BIN}"
assert_file_exists "${ORCHESTRATOR_MODE_BIN}"
assert_file_exists "${RUNTIME_ROUTING_CONFIG}"

if [[ ! -x "${ORCHESTRATOR_ROUTING_BIN}" ]]; then
  echo "[FAIL] orchestrator-routing is not executable" >&2
  FAILED=1
else
  echo "[PASS] orchestrator-routing is executable"
  if ! PYTHONDONTWRITEBYTECODE=1 "${ORCHESTRATOR_ROUTING_BIN}" --config-path "${RUNTIME_ROUTING_CONFIG}" validate >/dev/null 2>&1; then
    echo "[FAIL] Installed runtime-routing.yaml validation failed" >&2
    FAILED=1
  else
    echo "[PASS] Installed runtime-routing.yaml is valid"
  fi
fi
echo "--- Verifying Installed Commands Execute Read-Only ---"
if [[ ! -x "${DOCTOR}" ]]; then
    echo "[FAIL] Doctor is not executable: ${DOCTOR}" >&2
    FAILED=1
else
    echo "[PASS] Doctor is executable"
    if ! PYTHONDONTWRITEBYTECODE=1 "${DOCTOR}" --config "${MODELS_CONFIG}" --target-home "${TARGET_HOME}" >/dev/null 2>&1; then
      echo "[FAIL] Installed Doctor failed read-only execution" >&2
      FAILED=1
    else
      echo "[PASS] Installed Doctor executed read-only"
    fi
fi

if [[ ! -x "${CONFIGURE_MODELS}" ]]; then
    echo "[FAIL] configure-models is not executable: ${CONFIGURE_MODELS}" >&2
    FAILED=1
else
    echo "[PASS] configure-models is executable"
    if ! PYTHONDONTWRITEBYTECODE=1 "${CONFIGURE_MODELS}" --config "${MODELS_CONFIG}" >/dev/null 2>&1; then
      echo "[FAIL] Installed configure-models failed read-only execution" >&2
      FAILED=1
    else
      echo "[PASS] configure-models executed read-only"
    fi
fi

echo "--- Verifying Canonical Auto Team Policy Planes ---"
if ! PYTHONDONTWRITEBYTECODE=1 python3 - "${MODELS_CONFIG}" "${RUNTIME_ROUTING_CONFIG}" <<'PY_POLICY'
import sys
from pathlib import Path

import yaml

models_path = Path(sys.argv[1])
runtime_path = Path(sys.argv[2])
roles = (
    "BOSS",
    "SCOUT",
    "STANDARD_WORKER",
    "DEEP_WORKER",
    "VERIFIER",
    "PREMIUM_SECOND_OPINION",
)
advisory_roles = {
    "planner": "BOSS",
    "scout": "SCOUT",
    "worker": "STANDARD_WORKER",
    "reviewer": "VERIFIER",
}

try:
    models = yaml.safe_load(models_path.read_text(encoding="utf-8"))
    runtime = yaml.safe_load(runtime_path.read_text(encoding="utf-8"))
except Exception as exc:
    raise SystemExit(f"policy-plane YAML read/parse failure: {exc}")

if not isinstance(models, dict) or not isinstance(runtime, dict):
    raise SystemExit("policy-plane roots must be mappings")

models_operator = models.get("operator_policy")
runtime_operator = runtime.get("operator_policy")
if not isinstance(models_operator, dict) or not isinstance(runtime_operator, dict):
    raise SystemExit("both policy planes must define operator_policy mappings")
if set(models_operator) != set(roles) or set(runtime_operator) != set(roles):
    raise SystemExit("operator_policy roles are not exactly the six canonical roles")

endpoint_resolution = runtime.get("endpoint_resolution")
if not isinstance(endpoint_resolution, dict):
    raise SystemExit("runtime endpoint_resolution must be a mapping")

for role in roles:
    raw_entries = models_operator[role]
    runtime_entries = runtime_operator[role]
    if not isinstance(raw_entries, list) or not raw_entries:
        raise SystemExit(f"models.yaml operator_policy.{role} is empty or invalid")
    if not isinstance(runtime_entries, list) or not runtime_entries:
        raise SystemExit(f"runtime operator_policy.{role} is empty or invalid")

    raw_chain = []
    for entry in raw_entries:
        if not isinstance(entry, dict) or set(entry) != {"model", "effort"}:
            raise SystemExit(f"models.yaml operator_policy.{role} entry is invalid")
        raw_chain.append((entry["model"], entry["effort"]))

    translated = []
    for model, effort in raw_chain:
        matches = [
            endpoint
            for endpoint, metadata in endpoint_resolution.items()
            if isinstance(metadata, dict)
            and metadata.get("model") == model
            and metadata.get("effort") == effort
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"models.yaml operator_policy.{role} identity "
                f"{model!r}/{effort!r} maps to {len(matches)} runtime endpoints"
            )
        translated.append(
            {"endpoint": matches[0], "model": model, "effort": effort}
        )

    if runtime_entries != translated:
        raise SystemExit(
            f"runtime operator_policy.{role} is not the exact deterministic "
            "translation of models.yaml"
        )

for advisory_role, operator_role in advisory_roles.items():
    entry = models.get(advisory_role)
    if not isinstance(entry, dict):
        raise SystemExit(f"models.yaml advisory role {advisory_role} is invalid")
    projected = list(entry.get("preferred", [])) + list(entry.get("fallback", []))
    expected = [item["model"] for item in models_operator[operator_role]]
    if projected != expected:
        raise SystemExit(
            f"models.yaml {advisory_role} preferred+fallback is not the "
            f"exact projection of operator_policy.{operator_role}"
        )

print("[PASS] Canonical Auto Team policy and advisory/runtime translations validated")
PY_POLICY
then
  echo "[FAIL] Canonical Auto Team policy-plane consistency failed" >&2
  FAILED=1
fi

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
done

# 3. Dedicated Opus 4.6 Thinking Isolation Checks
echo "--- Verifying Opus Read-Only Isolation ---"
assert_contains "${CORE}" "role: PREMIUM_SECOND_OPINION" "Core registers Opus as PREMIUM_SECOND_OPINION"
assert_contains "${CORE}" "access: READ_ONLY" "Core specifies Opus access is READ_ONLY"
assert_contains "${CORE}" "write_ownership: NONE" "Core specifies Opus write ownership is NONE"

# 4. Context & Packet Isolation
echo "--- Verifying Context & Packet Contracts ---"
assert_contains "${CORE}" "fork_turns=\"none\"" "Core enforces fork_turns='none'"
assert_contains "${CORE}" "BOSS_MISSION_PACKET:" "Boss mission packet schema defined"
assert_contains "${CORE}" "BOSS_ACTION_PACKET:" "Boss action packet schema defined"
assert_contains "${CORE}" "CHILD_EXECUTION_RESULT:" "Child execution result schema defined"
assert_contains "${CORE}" "BOSS_FOLLOWUP_PACKET:" "Boss followup packet schema defined"
assert_contains "${CORE}" "FINAL_BOSS_DECISION:" "Final Boss decision schema defined"
assert_contains "${CORE}" "WORKER_TASK_PACKET:" "Worker task packet schema defined"
assert_contains "${CORE}" "VERIFICATION_PACKET:" "Verification packet schema defined"
assert_contains "${CORE}" "prior_attempt_summary:" "Rework schema defined"
assert_contains "${CORE}" "PACKET_INVALID" "Packet invalidity rule defined"
assert_contains "${CORE}" "Pre-Execution Invariant" "Packet failure blocks worker spawn without provider fallback"
assert_contains "${CORE}" "HOST_MODEL_BINDING_REQUIRED" "Core requires explicit native Host model binding"
assert_contains "${CORE}" "HOST_MODEL_BINDING_ERROR" "Core defines fail-closed Host binding error"
assert_contains "${CORE}" "HOST_AGENT_NAME_REQUIRED" "Core requires valid native Host task names"
assert_contains "${CORE}" "HOST_AGENT_NAME_INVALID" "Core defines invalid Host task-name error"
assert_contains "${CORE}" "host_spawn_request" "Core records native Host spawn request"
assert_contains "${AUTOTEAM_SKILL}" "^[a-z0-9_]+$" "Auto Team validates bare lowercase Host task names"
assert_contains "${AUTOTEAM_SKILL}" "HOST_AGENT_NAME_INVALID" "Auto Team fails closed on invalid Host task names"
assert_contains "${CORE}" "effective_model" "Core records Host effective model identity"
assert_contains "${AUTOTEAM_SKILL}" "model: <validated requested_model>" "Auto Team passes model to spawn_agent"
assert_contains "${AUTOTEAM_SKILL}" "reasoning_effort: <validated requested_effort>" "Auto Team passes effort to spawn_agent"
assert_contains "${AUTOTEAM_SKILL}" "parent/default model" "Auto Team forbids parent-model inheritance fallback"

# 5. Dedicated Boss & Plane Separation Checks
echo "--- Verifying Dedicated Boss & Plane Separation Invariants ---"
assert_contains "${CORE}" "ROOT_CONTROLLER_MUST_NOT_SELF_PROMOTE" "Core enforces Root Controller cannot self-promote"
assert_contains "${CORE}" "DEDICATED_BOSS_REQUIRED" "Core enforces Dedicated Boss is mandatory"
assert_contains "${CORE}" "DEDICATED_BOSS_CONTINUITY_REQUIRED" "Core enforces Dedicated Boss continuity across turns"
assert_contains "${AUTOTEAM_SKILL}" "Root Controller" "Auto Team wrapper defines Root Controller"
assert_contains "${AUTOTEAM_SKILL}" "Dedicated Boss Mandatory" "Auto Team wrapper enforces Dedicated Boss requirement"
assert_contains "${AUTOTEAM_SKILL}" "BOSS_BINDING_UNAVAILABLE" "Auto Team wrapper fails closed on Boss binding failure"

# 6. Verification Invariant & Exhaustion
echo "--- Verifying Independent Verification & Exhaustion ---"
assert_contains "${CORE}" "IMPLEMENTER_MUST_NOT_VERIFY_ITS_OWN_WORK" "Core enforces verifier != implementer"
assert_contains "${CORE}" "VERIFIER_CHAIN_EXHAUSTED" "Core defines verifier chain exhaustion"
assert_contains "${CORE}" "Under NO circumstances may the implementer be used to self-verify" "Core forbids self-verification on exhaustion"

# 7. Mutation Safety
echo "--- Verifying Mutation Safety ---"
assert_contains "${CORE}" "AMBIGUOUS_EXECUTION_STATE" "Core defines ambiguous write state"
assert_contains "${CORE}" "Automatic fallback is **FORBIDDEN**" "Core forbids automatic fallback on ambiguous write"

# 8. Mission Trace Specification
echo "--- Verifying Mission Trace Invariants ---"
assert_contains "${CORE}" "Runtime Mission Trace Specification" "Core defines Mission Trace Specification"
assert_contains "${CORE}" "~/.codex/orchestrator-traces/<mission_id>.json" "Core defines trace path"
assert_contains "${CORE}" "Trace Security & Privacy Invariant" "Core defines trace privacy/security invariant"

# 9. Dynamic Routing & Policy Correctness Verification
echo "--- Dynamically Verifying Routing Policy & Safety Invariants ---"
if ! python3 -c '
import json, os, re, sys, tomllib, yaml
from pathlib import Path

core_path = sys.argv[1]
agent_paths = sys.argv[2:10]
config_paths = sys.argv[10:12]
manifest_path = sys.argv[12] if len(sys.argv) > 12 else ""
target_home = Path(sys.argv[13]).resolve() if len(sys.argv) > 13 else None
toml_failures = []

omitted_paths = set()
if manifest_path and target_home is not None:
    try:
        raw_manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        omitted_paths = set(raw_manifest.get("migration_omissions", {}))
    except (OSError, ValueError, json.JSONDecodeError):
        pass

def is_omitted(path):
    if not omitted_paths:
        return False
    try:
        candidate = Path(path).resolve()
        if target_home is not None and candidate.is_relative_to(target_home):
            rel = str(candidate.relative_to(target_home))
            return rel in omitted_paths
    except Exception:
        pass
    return False

def toml_fail(path, reason):
    print(f"[FAIL] {path}: {reason}", file=sys.stderr)
    toml_failures.append(path)

def require(path, condition, reason):
    if not condition:
        toml_fail(path, reason)

def load_toml(path):
    if not os.path.exists(path):
        if is_omitted(path):
            print(f"[SKIP] Explicit migration omission (absent): {path}")
            return None
        toml_fail(path, f"missing required file: {path}")
        return None
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        toml_fail(path, f"TOML parse error: {exc}")
        return None
expected_agents = {
    "luna_max_worker.toml": {
        "kind": "luna",
        "name": "luna_max_worker",
        "model": "gpt-5.6-luna",
    },
    "router-model-nine-router-ag-claude-opus-4-6-thinking.toml": {
        "kind": "router",
        "name": "router_nine_router_ag_claude_opus_4_6_thinking",
        "model": "nine-router/ag/claude-opus-4-6-thinking",
    },
    "router-model-nine-router-ag-gemini-3-7-flash-high.toml": {
        "kind": "router",
        "name": "router_nine_router_ag_gemini_3_7_flash_high",
        "model": "nine-router/ag/gemini-3.7-flash-high",
    },
    "router-model-opencode-go-deepseek-v4-flash.toml": {
        "kind": "router",
        "name": "router_opencode_go_deepseek_v4_flash",
        "model": "opencode-go/deepseek-v4-flash",
    },
    "router-model-opencode-go-deepseek-v4-pro.toml": {
        "kind": "router",
        "name": "router_opencode_go_deepseek_v4_pro",
        "model": "opencode-go/deepseek-v4-pro",
    },
    "router-model-opencode-go-responses-gpt-5-6-luna.toml": {
        "kind": "router",
        "name": "router_opencode_go_responses_gpt_5_6_luna",
        "model": "opencode-go-responses/gpt-5.6-luna",
    },
    "router-model-custom-qwen3-8-27b.toml": {
        "kind": "router",
        "name": "router_custom_qwen3_8_27b",
        "model": "custom/qwen3.8-27b",
    },
    "router-model-nine-router-stepplan-step-3-7-flash.toml": {
        "kind": "router",
        "name": "router_nine_router_stepplan_step_3_7_flash",
        "model": "nine-router/stepplan/step-3.7-flash",
    },
}

safety_phrases = (
    "Hub-and-Spoke",
    "Do not spawn, delegate to, or orchestrate additional agents or subagents.",
    "Do not communicate directly with peer workers or reviewers.",
    "Do not create nested delegation chains.",
    "Return your result only to the parent Boss.",
    "A parent request to spawn another agent does not override this restriction.",
)

agent_data = {}
for path in agent_paths:
    parsed = load_toml(path)
    if parsed is not None:
        agent_data[path] = parsed

for path, data in agent_data.items():
    if is_omitted(path):
        print(f"[SKIP] Explicit migration omission: {path}")
        continue
    filename = os.path.basename(path)
    expected = expected_agents.get(filename)
    if expected is None:
        toml_fail(path, "unexpected agent declaration")
        continue
    if type(data) is not dict:
        toml_fail(path, "root must be a TOML table")
        continue

    if expected["kind"] == "luna":
        expected_keys = {"name", "description", "model", "model_reasoning_effort", "developer_instructions"}
    else:
        expected_keys = {"name", "description", "model_provider", "model", "developer_instructions"}
    require(path, set(data) == expected_keys, f"root keys must be exactly {sorted(expected_keys)}")

    for key in expected_keys:
        require(path, type(data.get(key)) is str, f"{key} must be a string")
    if type(data.get("name")) is str:
        require(path, data["name"] == expected["name"], "name must be {!r}".format(expected["name"]))
    if type(data.get("model")) is str:
        require(path, data["model"] == expected["model"], "model must be {!r}".format(expected["model"]))
    if expected["kind"] == "luna":
        if type(data.get("model_reasoning_effort")) is str:
            require(path, data["model_reasoning_effort"] == "max", "model_reasoning_effort must be 'max'")
    else:
        if type(data.get("model_provider")) is str:
            require(path, data["model_provider"] == "codex-router", "model_provider must be 'codex-router'")

    instructions = data.get("developer_instructions")
    if type(instructions) is str:
        for phrase in safety_phrases:
            require(path, phrase in instructions, f"developer_instructions missing required phrase {phrase!r}")
        require(path, "unless the parent explicitly instructs" not in instructions.lower(), "developer_instructions contains a conditional escape hatch")
        if filename == "router-model-nine-router-ag-claude-opus-4-6-thinking.toml":
            require(path, "You are a read-only independent reviewer" in instructions, "Opus prompt must be read-only")
            require(path, "Do not modify, create, rename, or delete project files." in instructions, "Opus prompt must forbid file mutations")
            require(path, "Do not perform implementation." in instructions, "Opus prompt must forbid implementation")

config_data = {}
for path in config_paths:
    parsed = load_toml(path)
    if parsed is not None:
        config_data[path] = parsed

for path, data in config_data.items():
    filename = os.path.basename(path)
    if filename == "sol-luna.config.toml":
        require(path, type(data) is dict, "root must be a TOML table")
        if type(data) is not dict:
            continue
        require(path, set(data) == {"model", "model_reasoning_effort", "agents"}, "root keys must be exactly ['agents', 'model', 'model_reasoning_effort']")
        require(path, type(data.get("model")) is str, "model must be a string")
        require(path, type(data.get("model_reasoning_effort")) is str, "model_reasoning_effort must be a string")
        require(path, data.get("model") == "gpt-5.6-sol", "model must be 'gpt-5.6-sol'")
        require(path, data.get("model_reasoning_effort") == "high", "model_reasoning_effort must be 'high'")
        agents = data.get("agents")
        require(path, type(agents) is dict, "agents must be a table")
        if type(agents) is dict:
            require(path, set(agents) == {"max_threads", "interrupt_message", "luna_max_worker"}, "agents keys must be exactly ['interrupt_message', 'luna_max_worker', 'max_threads']")
            require(path, type(agents.get("max_threads")) is int, "agents.max_threads must be an integer")
            require(path, agents.get("max_threads") == 6, "agents.max_threads must be 6")
            require(path, type(agents.get("interrupt_message")) is bool, "agents.interrupt_message must be a boolean")
            require(path, agents.get("interrupt_message") is True, "agents.interrupt_message must be true")
            luna = agents.get("luna_max_worker")
            require(path, type(luna) is dict, "agents.luna_max_worker must be a table")
            if type(luna) is dict:
                require(path, set(luna) == {"description", "config_file"}, "agents.luna_max_worker keys must be exactly ['config_file', 'description']")
                require(path, type(luna.get("description")) is str, "agents.luna_max_worker.description must be a string")
                require(path, luna.get("description") == "A focused GPT-5.6 Luna Max worker for narrow, bounded tasks delegated by the Sol High orchestration parent.", "agents.luna_max_worker.description is not canonical")
                require(path, type(luna.get("config_file")) is str, "agents.luna_max_worker.config_file must be a string")
                require(path, luna.get("config_file") == "agents/luna_max_worker.toml", "agents.luna_max_worker.config_file is not canonical")
    elif filename == "grok-v2.config.toml":
        require(path, type(data) is dict, "root must be a TOML table")
        if type(data) is not dict:
            continue
        require(path, set(data) == {"model", "model_reasoning_effort", "agents"}, "root keys must be exactly ['agents', 'model', 'model_reasoning_effort']")
        require(path, type(data.get("model")) is str, "model must be a string")
        require(path, type(data.get("model_reasoning_effort")) is str, "model_reasoning_effort must be a string")
        require(path, data.get("model") == "nine-router/gcli/grok-4.6-high", "model must be 'nine-router/gcli/grok-4.6-high'")
        require(path, data.get("model_reasoning_effort") == "high", "model_reasoning_effort must be 'high'")
        agents = data.get("agents")
        require(path, type(agents) is dict, "agents must be a table")
        if type(agents) is dict:
            require(path, set(agents) == {"max_threads", "interrupt_message"}, "agents keys must be exactly ['interrupt_message', 'max_threads']")
            require(path, type(agents.get("max_threads")) is int, "agents.max_threads must be an integer")
            require(path, agents.get("max_threads") == 6, "agents.max_threads must be 6")
            require(path, type(agents.get("interrupt_message")) is bool, "agents.interrupt_message must be a boolean")
            require(path, agents.get("interrupt_message") is True, "agents.interrupt_message must be true")
    else:
        toml_fail(path, "unexpected config profile")

if toml_failures:
    print(f"[FAIL] TOML validation failed ({len(toml_failures)} issue(s))", file=sys.stderr)
    sys.exit(1)

print(f"[PASS] Agent TOML schemas and canonical mappings validated ({len(agent_data)} agents)")
print(f"[PASS] Config TOML schemas and canonical values validated ({len(config_data)} profiles)")

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

# B. Skill Boss Bindings Verification
skill_bindings = parsed_data.get("skill_boss_bindings")
if not skill_bindings or not isinstance(skill_bindings, dict):
    print("[FAIL] skill_boss_bindings missing or invalid in Core", file=sys.stderr)
    sys.exit(1)

for skill_name, s_info in skill_bindings.items():
    req_ep = s_info.get("required_boss_endpoint")
    if req_ep not in endpoint_map:
        print(f"[FAIL] Skill {skill_name} requires unknown Boss endpoint {req_ep}", file=sys.stderr)
        sys.exit(1)
    ep = endpoint_map[req_ep]
    model = s_info.get("model")
    if model and ep.get("model") and model != ep.get("model"):
        print(f"[FAIL] Model mismatch for Boss endpoint {req_ep} in skill {skill_name}: expected {ep.get('model')}, got {model}", file=sys.stderr)
        sys.exit(1)
    eff = s_info.get("effort")
    if eff not in ep.get("accepted_efforts", []):
        print(f"[FAIL] Boss effort {eff} for {req_ep} in skill {skill_name} not in accepted_efforts", file=sys.stderr)
        sys.exit(1)

print(f"[PASS] Skill Boss bindings validated dynamically ({len(skill_bindings)} skills)")

# C. Dynamic Role Chains Verification
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

# D. Dynamic Verifier Chains Verification
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
' "${CORE}" \
  "${CODEX_AGENTS}/luna_max_worker.toml" \
  "${CODEX_AGENTS}/router-model-nine-router-ag-claude-opus-4-6-thinking.toml" \
  "${CODEX_AGENTS}/router-model-nine-router-ag-gemini-3-7-flash-high.toml" \
  "${CODEX_AGENTS}/router-model-opencode-go-deepseek-v4-flash.toml" \
  "${CODEX_AGENTS}/router-model-opencode-go-deepseek-v4-pro.toml" \
  "${CODEX_AGENTS}/router-model-opencode-go-responses-gpt-5-6-luna.toml" \
  "${CODEX_AGENTS}/router-model-custom-qwen3-8-27b.toml" \
  "${CODEX_AGENTS}/router-model-nine-router-stepplan-step-3-7-flash.toml" \
  "${SOL_CONFIG}" "${GROK_CONFIG}" "${MANIFEST_FILE}" "${TARGET_HOME}"; then
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
