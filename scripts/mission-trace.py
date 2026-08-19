#!/usr/bin/env bash
""":"
exec python3 "$0" "$@"
"""
import os, sys, json, argparse, re

TRACE_DIR = os.path.expanduser("~/.codex/orchestrator-traces")

def sanitize_trace_data(data):
    """
    Ensure no API keys, tokens, or auth headers are present in trace data.
    """
    sensitive_keys = {"authorization", "api_key", "token", "password", "secret", "bearer"}
    def _clean(obj):
        if isinstance(obj, dict):
            res = {}
            for k, v in obj.items():
                if any(sk in k.lower() for sk in sensitive_keys):
                    res[k] = "[REDACTED]"
                else:
                    res[k] = _clean(v)
            return res
        elif isinstance(obj, list):
            return [_clean(item) for item in obj]
        elif isinstance(obj, str):
            if re.search(r"(sk-[a-zA-Z0-9]{20,}|Bearer\s+[a-zA-Z0-9_\-\.]+)", obj):
                return "[REDACTED_SECRET]"
            return obj
        return obj
    return _clean(data)

def render_human_readable(trace_data):
    mission = trace_data.get("mission", {})
    controller = trace_data.get("controller", {})
    boss = trace_data.get("boss", {})
    actions = trace_data.get("actions", [])
    verification = trace_data.get("verification", {})
    rework = trace_data.get("rework", {})
    final = trace_data.get("final", {})

    lines = []
    lines.append("=" * 68)
    lines.append(f" MULTI ORCHESTRATOR MISSION TRACE: {mission.get('mission_id', 'UNKNOWN')}")
    lines.append("=" * 68)
    lines.append(f"Skill:               {mission.get('skill', 'UNKNOWN')}")
    lines.append(f"Status:              {mission.get('status', 'UNKNOWN')}")
    lines.append(f"Started At:          {mission.get('started_at', 'UNKNOWN')}")
    lines.append(f"Controller:          {controller.get('actual_session_model', 'UNKNOWN')} ({controller.get('role', 'ROOT_CONTROLLER')})")
    lines.append(f"Dedicated Boss:      {boss.get('actual_model', 'UNKNOWN')} (type: {boss.get('actual_agent_type', 'default')})")
    lines.append(f"Boss Requested:      {boss.get('requested_model', 'UNKNOWN')} / {boss.get('requested_effort', 'UNKNOWN')}")
    lines.append(f"Boss Child ID:       {boss.get('child_id', 'UNKNOWN')}")
    lines.append(f"Boss Binding:        {'PROVEN' if boss.get('binding_proven') else 'UNPROVEN'}")
    lines.append(f"Boss Continuity:     {'PROVEN' if boss.get('continuity_proven') else 'UNPROVEN'}")
    lines.append("-" * 68)
    lines.append("DELEGATED ACTIONS & WORKERS:")
    if not actions:
        lines.append("  (None recorded)")
    for idx, act in enumerate(actions):
        req = act.get("boss_requested", {})
        val = act.get("controller_validation", {})
        exe = act.get("controller_executed", {})
        res = act.get("result", {})
        val_reason = f" ({val.get('reason')})" if val.get('reason') else ""
        lines.append(f"  [{idx+1}] Action ID: {act.get('action_id', f'act-{idx+1}')} | Role: {act.get('role')} | Task: {act.get('logical_task_id')}")
        lines.append(f"      Intended:         {req.get('endpoint')} ({req.get('model')}/{req.get('effort')})")
        lines.append(f"      Validation:       {val.get('result')}{val_reason}")
        lines.append(f"      Executed Binding: {exe.get('actual_model')} (type: {exe.get('agent_type')}, effort: {exe.get('actual_effort')})")
        lines.append(f"      Binding Match:    {act.get('binding_match')}")
        lines.append(f"      Result Status:    {res.get('status')} (mutation: {res.get('mutation_state')})")
        if res.get("errors"):
            lines.append(f"      Errors:           {', '.join(res.get('errors'))}")
    lines.append("-" * 68)
    lines.append("VERIFICATION & REWORK:")
    lines.append(f"  Implementer:       {verification.get('implementer', 'N/A')}")
    lines.append(f"  Verifier:          {verification.get('verifier', 'N/A')}")
    lines.append(f"  Independence:      {verification.get('independent', False)} (model family: {verification.get('model_family_independent', False)})")
    lines.append(f"  Result:            {verification.get('result', 'N/A')}")
    lines.append(f"  Rework Count:      {rework.get('count', 0)}")
    lines.append("-" * 68)
    lines.append("FINAL OUTCOME:")
    lines.append(f"  Boss Decision:     {final.get('boss_decision', 'UNKNOWN')}")
    lines.append(f"  Mission Result:    {final.get('mission_result', 'UNKNOWN')}")
    if final.get("summary"):
        lines.append(f"  Summary:           {final.get('summary')}")
    lines.append("=" * 68)
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Multi Orchestrator Mission Trace Reader")
    parser.add_argument("mission_id", nargs="?", default="latest", help="Mission ID or 'latest' (default: latest)")
    parser.add_argument("--json", action="store_true", help="Output raw sanitized JSON")
    parser.add_argument("--trace-dir", default=TRACE_DIR, help=f"Custom trace directory (default: {TRACE_DIR})")
    args = parser.parse_args()

    trace_dir = os.path.expanduser(args.trace_dir)
    if not os.path.exists(trace_dir):
        print(f"[ERROR] Trace directory does not exist: {trace_dir}", file=sys.stderr)
        sys.exit(1)

    if args.mission_id == "latest":
        files = [os.path.join(trace_dir, f) for f in os.listdir(trace_dir) if f.endswith(".json")]
        if not files:
            print("[INFO] No mission traces found.", file=sys.stderr)
            sys.exit(0)
        target_file = max(files, key=os.path.getmtime)
    else:
        target_file = os.path.join(trace_dir, f"{args.mission_id}.json" if not args.mission_id.endswith(".json") else args.mission_id)

    if not os.path.exists(target_file):
        print(f"[ERROR] Trace file not found: {target_file}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to parse trace file {target_file}: {e}", file=sys.stderr)
        sys.exit(1)

    sanitized = sanitize_trace_data(data)
    if args.json:
        print(json.dumps(sanitized, indent=2))
    else:
        print(render_human_readable(sanitized))

if __name__ == "__main__":
    main()
