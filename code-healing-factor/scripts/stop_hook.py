#!/usr/bin/env python3
"""Optional, explicitly armed Stop hook. Never runs checks or modifies state."""
import argparse
import json
from pathlib import Path
import sys

from heal import LEVELS, SKILL, config, fingerprint, policy, read

WARNING = {"systemMessage": "Code Healing Factor could not verify completion for this turn."}


def respond(event, root, plan_file, state):
    if event.get("hook_event_name") != "Stop":
        return {}
    if not (state / "arm.json").is_file():
        return {}
    try:
        arm = read(state / "arm.json")
        keys = ("session_id", "turn_id")
        if any(not isinstance(event.get(key), str) or not event[key] or
               arm.get(key) != event[key] for key in keys):
            return {}
        if Path(event["cwd"]).resolve() != root:
            return {}
        active = event.get("stop_hook_active")
        if type(active) is not bool or arm.get("cancelled") is not False:
            return {}
        if (state / ".lock").exists():
            return WARNING
        plan = config(plan_file)
        stamp = fingerprint(root, plan["source"], plan.get("exclude", []))
        report_file = state / "report.json"
        report = read(report_file) if report_file.is_file() else {}
        required = set(plan["required"]).union(LEVELS[plan["level"]])
        if (report.get("status") == "PASS" and report.get("completed") is True and
                report.get("verification_protocol") == 2 and report.get("finalized") is True and
                report.get("skill") == SKILL and report.get("schema_version") == "1.0" and
                report.get("project") == str(root) and report.get("source_fingerprint") == stamp and
                report.get("checked_fingerprint") == stamp and report.get("plan") == plan and
                report.get("run_started_ns", report_file.stat().st_mtime_ns) >=
                (state / "arm.json").stat().st_mtime_ns and
                report.get("blockers") == [] and
                "FAIL" not in report["gates"].values() and
                all(report["gates"].get(gate) == "PASS" for gate in required)):
            return {}
        history_file = state / "history.json"
        history = read(history_file) if history_file.is_file() else {"project": str(root), "attempts": []}
        if history.get("project") != str(root):
            return WARNING
        if active or policy(plan["repair"], history["attempts"]).startswith("STOP"):
            return WARNING
        return {"decision": "block",
                "reason": "Finish the scoped verification once if authorized and feasible. "
                          "Otherwise report the remaining failed or blocked gates and stop."}
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return WARNING


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "plan", "state"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(1024 * 1024 + 1)
        event = json.loads(raw) if len(raw) <= 1024 * 1024 else None
        reply = respond(event, args.root.resolve(), args.plan, args.state) if isinstance(event, dict) else {}
    except (UnicodeError, ValueError):
        reply = {}
    print(json.dumps(reply))


if __name__ == "__main__":
    main()
