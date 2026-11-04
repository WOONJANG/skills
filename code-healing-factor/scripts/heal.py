#!/usr/bin/env python3
"""Run project checks and evaluate evidence without modifying project source."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import stat
import subprocess
import sys
import tempfile
from threading import Thread
import time
from uuid import uuid4
from xml.etree import ElementTree

GATES = tuple(f"G{i:02}" for i in range(1, 15))
EXECUTION = {"G04", "G05", "G06", "G07", "G08", "G09", "G11"}
LEVELS = {
    "LIGHT": {"G01", "G14"},
    "STANDARD": {"G01", "G02", "G03", "G11", "G12", "G14"},
    "STRICT": {"G01", "G02", "G03", "G07", "G08", "G09", "G10",
               "G11", "G12", "G13", "G14"},
}
SEVERITIES = ("INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL")
EXIT = {"PASS": 0, "FAILED": 1, "BLOCKED": 2}
MARKERS = {
    "pyproject.toml": "Python", "requirements.txt": "Python", "pytest.ini": "Python",
    "package.json": "JavaScript/TypeScript", "composer.json": "PHP",
    "Cargo.toml": "Rust", "go.mod": "Go", "pom.xml": "Java", "Gemfile": "Ruby",
}
SKILL = "code-healing-factor"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(directory):
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".lock"
    lock.mkdir()
    try:
        yield
    finally:
        lock.rmdir()


def relative(value, root):
    path = Path(value)
    require(not path.is_absolute() and not path.anchor and ".." not in path.parts,
            "Expected a project-relative path without parent traversal")
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root), "Path escapes project")
    return root / path


def source_files(root, source, exclude=()):
    """Enumerate explicit fingerprint inputs without following links."""
    excluded = {relative(item, root) for item in exclude}
    files = set()
    pending = [relative(item, root) for item in source]
    while pending:
        path = pending.pop()
        if path in excluded or path.name in {".git", "__pycache__"}:
            continue
        info = path.lstat()
        require(not (path.is_symlink() or getattr(info, "st_file_attributes", 0) & 1024),
                "Linked or reparse-point source needs explicit review")
        if stat.S_ISDIR(info.st_mode):
            pending.extend(path.iterdir())
        else:
            require(stat.S_ISREG(info.st_mode), "Source input must be a regular file")
            files.add(path)
    require(files, "Source inputs contain no files")
    return files


def fingerprint(root, source, exclude=()):
    digest = hashlib.sha256()
    files = source_files(root, source, exclude)
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        name = path.relative_to(root).as_posix().encode("utf-8")
        with path.open("rb") as stream:
            content = hashlib.file_digest(stream, "sha256").digest()
        digest.update(len(name).to_bytes(8, "big") + name + content)
    return digest.hexdigest()


def git_scope(root, plan):
    """Report visible Git changes outside the current fingerprint inputs."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all",
             "--", "."],
            cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=10, check=False,
        )
        if result.returncode:
            return {"status": "UNAVAILABLE"}
        # Porcelain v1 paths are relative to the Git root, including from subdirectories.
        top = subprocess.run(
            ["git", "rev-parse", "--show-prefix"], cwd=root, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10, check=True,
        ).stdout.decode("utf-8", errors="surrogateescape").rstrip("\r\n")
        changed = {Path(entry[3:]).relative_to(Path(top)) for entry in
                   result.stdout.decode("utf-8", errors="surrogateescape").split("\0") if entry}
        tracked = {path.relative_to(root) for path in
                   source_files(root, plan["source"], plan.get("exclude", []))}
        return {"status": "CHECKED",
                "outside_fingerprint": sorted(path.as_posix() for path in changed - tracked)}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"status": "UNAVAILABLE"}


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def config(path):
    plan = read(path)
    require(isinstance(plan, dict) and plan.get("schema_version") == "1.0",
            "Plan schema_version must be 1.0")
    require(set(plan) <= {"schema_version", "source", "exclude", "level", "required",
                          "checks", "limits", "security_threshold", "repair", "requirements"},
            "Unknown plan field")
    for field in ("source", "exclude"):
        values = plan.get(field, [])
        require(isinstance(values, list) and all(isinstance(v, str) and v for v in values),
                f"Invalid {field} paths")
    require(plan.get("source"), "Specify relevant source, test and configuration inputs")
    level = plan.get("level", "STANDARD")
    require(level in LEVELS, "Unknown verification level")
    required = plan.get("required", [])
    require(isinstance(required, list) and all(gate in GATES for gate in required),
            "Invalid required gates")
    plan["required"] = sorted(LEVELS[level].union(required))
    plan["level"] = level
    limits = {"timeout": 60, "total_seconds": 600, "workers": 1, "stdout_bytes": 1048576}
    overrides = plan.get("limits", {})
    require(isinstance(overrides, dict) and overrides.keys() <= limits.keys(),
            "Unknown execution limit")
    limits.update(overrides)
    require(integer(limits["timeout"], 1, 3600) and
            integer(limits["total_seconds"], 1, 14400) and integer(limits["workers"], 1, 8) and
            integer(limits["stdout_bytes"], 1, 16777216),
            "Invalid execution limits")
    plan["limits"] = limits
    repair = {"max_iterations": 8, "no_progress_threshold": 2,
              "change_strategy_on_stagnation": True}
    overrides = plan.get("repair", {})
    require(isinstance(overrides, dict) and overrides.keys() <= repair.keys(),
            "Unknown repair setting")
    repair.update(overrides)
    require(integer(repair["max_iterations"], 1, 100) and
            integer(repair["no_progress_threshold"], 1, 100) and
            type(repair["change_strategy_on_stagnation"]) is bool, "Invalid repair policy")
    plan["repair"] = repair
    threshold = plan.get("security_threshold", "HIGH")
    require(threshold in SEVERITIES, "Invalid security threshold")
    plan["security_threshold"] = threshold
    checks = plan.get("checks", [])
    require(isinstance(checks, list), "Checks must be an array")
    ids = set()
    for check in checks:
        require(isinstance(check, dict) and
                set(check) <= {"id", "gate", "argv", "cwd", "timeout", "stdout_sha256",
                               "junit", "diagnostics"},
                "Invalid check fields")
        ident, argv = check.get("id"), check.get("argv")
        require(isinstance(ident, str) and ident.strip() and ident not in ids,
                "Each check needs a unique ID")
        ids.add(ident)
        require(check.get("gate") in GATES and isinstance(argv, list) and argv and argv[0] and
                all(isinstance(arg, str) and "\0" not in arg for arg in argv),
                "Each check needs a gate and valid argv")
        require(isinstance(check.get("cwd", "."), str) and
                integer(check.get("timeout", limits["timeout"]), 1, 3600),
                "Invalid check cwd or timeout")
        require(all(type(check.get(field, False)) is bool for field in ("junit", "diagnostics")),
                "junit and diagnostics must be boolean")
        require(not check.get("junit") or any("{junit}" in arg for arg in argv[1:]),
                "JUnit checks must pass {junit} in argv")
        oracle = check.get("stdout_sha256")
        require(oracle is None or (isinstance(oracle, str) and len(oracle) == 64 and
                                   all(ch in "0123456789abcdef" for ch in oracle)),
                "Expected lowercase stdout SHA-256")
    requirements = plan.get("requirements", {})
    require(isinstance(requirements, dict), "Requirements must map IDs to execution check IDs")
    execution_ids = {check["id"] for check in checks if check["gate"] in EXECUTION}
    for ident, links in requirements.items():
        require(ident.strip() and isinstance(links, list) and links and
                all(isinstance(link, str) and link in execution_ids for link in links) and
                len(links) == len(set(links)),
                f"Invalid execution check links for requirement {ident}")
    if "requirements" in plan:
        require(requirements, "Requirements must contain at least one mapping")
    return plan


def now():
    return datetime.now(timezone.utc).isoformat()


def output_digest(argv, cwd, seconds, limit):
    """Read stdout incrementally, keeping memory bounded by one chunk."""
    deadline = time.monotonic() + seconds
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, stdout=subprocess.PIPE)
    result = Queue()

    def consume():
        size = 0
        digest = hashlib.sha256()
        try:
            with process.stdout as stream:
                for chunk in iter(stream.read1, b""):
                    size += len(chunk)
                    if size > limit:
                        result.put(None)
                        return
                    digest.update(chunk)
            result.put(digest.hexdigest())
        except OSError:
            result.put(None)

    Thread(target=consume, daemon=True).start()
    try:
        actual = result.get(timeout=max(0, deadline - time.monotonic()))
        if actual is None:
            return None, None
        return process.wait(timeout=max(0, deadline - time.monotonic())), actual
    except Empty:
        raise subprocess.TimeoutExpired(argv, seconds) from None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def junit_totals(root):
    totals = {}
    consistent = True
    suite_tags = {"testsuite", "testsuites"}
    for suite in reversed(list(root.iter())):
        if suite.tag not in suite_tags:
            continue
        cases = suite.findall("testcase")
        children = [totals[child] for child in suite if child.tag in suite_tags]
        tests = len(cases) + sum(child[0] for child in children)
        skipped = (sum(case.find("skipped") is not None for case in cases)
                   + sum(child[1] for child in children))
        failed = (sum(case.find("failure") is not None or case.find("error") is not None
                      for case in cases) + len(suite.findall("error"))
                  + len(suite.findall("failure")) + sum(child[2] for child in children))
        declared = {key: int(suite.attrib[key]) for key in ("tests", "skipped", "errors", "failures")
                    if key in suite.attrib}
        consistent &= (all(value >= 0 for value in declared.values())
                       and declared.get("tests", tests) == tests
                       and declared.get("skipped", skipped) == skipped)
        # Parent summaries include children. Do not count both as separate failures.
        failed = max(failed, declared.get("errors", 0) + declared.get("failures", 0))
        totals[suite] = tests, skipped, failed
    tests, skipped, failed = totals[root]
    if not consistent and not failed:
        return None
    return {"executed": tests - skipped, "skipped": skipped, "failed": failed}


def junit_counts(path):
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return None
        with path.open("rb") as stream:
            raw = stream.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            return None
        xml = raw.decode("utf-8-sig")
        if "<!DOCTYPE" in xml or "\0" in xml:
            return None
        root = ElementTree.fromstring(xml)
        if root.tag not in {"testsuites", "testsuite"}:
            return None
        return junit_totals(root)
    except (OSError, ValueError, ElementTree.ParseError):
        return None


def run_check(argv, cwd, seconds, limits, oracle):
    if oracle:
        return output_digest(argv, cwd, seconds, limits["stdout_bytes"])
    code = subprocess.run(argv, cwd=cwd, timeout=seconds, check=False,
                          stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL).returncode
    return code, None


def execute(check, root, limits, deadline, state=None):
    started = time.monotonic()
    argv = check["argv"][:]
    cwd = relative(check.get("cwd", "."), root)
    row = {"id": check["id"], "gate": check["gate"], "argv": argv[:],
           "cwd": str(cwd), "started": now(), "exit_code": None}
    seconds = min(check.get("timeout", limits["timeout"]), deadline - time.monotonic())
    status, reason = "BLOCKED", "Total command budget exhausted"
    if seconds > 0:
        if argv[0] == "{python}":
            argv[0] = sys.executable
        elif Path(argv[0]).name != argv[0]:
            argv[0] = str((cwd / argv[0]).resolve())
        else:
            argv[0] = shutil.which(argv[0]) or ""
        row["argv"][0] = argv[0] or row["argv"][0]
        if not argv[0]:
            reason = "Executable unavailable"
        elif os.name == "nt" and Path(argv[0]).suffix.lower() in {".cmd", ".bat"}:
            reason = "Use a native executable or explicit interpreter and script"
        else:
            try:
                oracle = check.get("stdout_sha256")
                counts = None
                if check.get("junit"):
                    with tempfile.TemporaryDirectory(dir=state) as directory:
                        result_path = Path(directory) / "result.xml"
                        command = [argv[0], *(arg.replace("{junit}", str(result_path))
                                              for arg in argv[1:])]
                        code, actual = run_check(command, cwd, seconds, limits, oracle)
                        counts = junit_counts(result_path)
                        row["test_counts"] = counts
                else:
                    code, actual = run_check(argv, cwd, seconds, limits, oracle)
                row["exit_code"] = code
                if code is None:
                    reason = "Stdout limit exceeded or output unavailable"
                elif code != 0:
                    status, reason = "FAIL", "Nonzero exit"
                elif actual != oracle:
                    status, reason = "FAIL", "Stdout digest mismatch"
                elif counts and counts["failed"]:
                    status, reason = "FAIL", "JUnit reported failed tests"
                elif check.get("junit") and (counts is None or not counts["executed"]):
                    reason = "JUnit report unavailable or no tests executed"
                else:
                    status, reason = "PASS", "Exit and configured oracle satisfied"
            except subprocess.TimeoutExpired:
                reason = "Command timeout"
            except OSError:
                reason = "Command could not start"
    row.update(status=status, reason=reason, ended=now())
    if check.get("diagnostics") and status != "PASS":
        row["diagnostics"] = {"reason": reason, "exit_code": row["exit_code"],
                              "duration_ms": round((time.monotonic() - started) * 1000),
                              "test_counts": row.get("test_counts")}
    return row


def assessment_matches(data, stamp, root):
    return data.get("fingerprint") == stamp and data.get("project") == str(root)


def assessment(data, stamp, root):
    require(isinstance(data, dict), "Invalid assessment")
    if not assessment_matches(data, stamp, root):
        return {}, []
    gates, issues = data.get("gates", {}), data.get("issues", [])
    require(isinstance(gates, dict) and isinstance(issues, list), "Invalid assessment")
    for gate, row in gates.items():
        require(gate in GATES and isinstance(row, dict) and
                row.get("status") in {"PASS", "FAIL", "BLOCKED", "NOT_APPLICABLE"} and
                isinstance(row.get("reason"), str) and row["reason"].strip(),
                "Each gate assessment needs a valid status and evidence or rationale")
        require(gate not in EXECUTION or row["status"] != "PASS",
                "Execution gates require recorded commands")
    ids = set()
    for issue in issues:
        require(isinstance(issue, dict) and
                all(isinstance(issue.get(key), str) and issue[key].strip()
                    for key in ("id", "category", "location", "evidence")) and
                issue.get("severity") in SEVERITIES and
                type(issue.get("blocking")) is bool and type(issue.get("resolved")) is bool,
                "Invalid issue record")
        require(issue["id"] not in ids, "Duplicate issue ID")
        ids.add(issue["id"])
    return gates, issues


def is_blocker(issue, plan):
    threshold = SEVERITIES.index(plan["security_threshold"])
    return not issue["resolved"] and (
        issue["blocking"] or (issue["category"] == "SECURITY_VULNERABILITY" and
                              SEVERITIES.index(issue["severity"]) >= threshold))


def evaluate(plan, rows, review, issues, stable):
    gates = {}
    for gate in GATES:
        states = [row["status"] for row in rows if row["gate"] == gate]
        if gate in review:
            states.append(review[gate]["status"])
        status = next((state for state in ("FAIL", "BLOCKED") if state in states), None)
        positive = ("PASS" in states if gate in EXECUTION else
                    review.get(gate, {}).get("status") == "PASS")
        status = status or ("PASS" if positive else
                            "NOT_APPLICABLE" if "NOT_APPLICABLE" in states else "NOT_RUN")
        gates[gate] = status if stable else "NOT_RUN"
    blockers = [issue["id"] for issue in issues if is_blocker(issue, plan)]
    if not stable:
        return "BLOCKED", gates, []
    if blockers or "FAIL" in gates.values():
        return "FAILED", gates, blockers
    required_checks = {link for links in plan.get("requirements", {}).values() for link in links}
    if (any(gates[gate] != "PASS" for gate in plan["required"])
            or any(row["status"] != "PASS" for row in rows if row["id"] in required_checks)):
        return "BLOCKED", gates, blockers
    return "PASS", gates, blockers


def policy(repair, attempts):
    if len(attempts) >= repair["max_iterations"]:
        return "STOP_LIMIT"
    trailing = 0
    for item in reversed(attempts):
        if item["progress"]:
            break
        trailing += 1
    threshold = repair["no_progress_threshold"]
    if trailing < threshold:
        return "CONTINUE"
    if not repair["change_strategy_on_stagnation"] or trailing > threshold:
        return "STOP_STAGNATION"
    return "CHANGE_STRATEGY"


def add_attempt(path, plan, root, item):
    history = read(path) if path.exists() else {"project": str(root), "attempts": []}
    require(history.get("project") == str(root), "History belongs to another project")
    attempts = history["attempts"]
    decision = policy(plan["repair"], attempts)
    require(not decision.startswith("STOP"), decision)
    require(isinstance(item, dict) and all(isinstance(item.get(k), str) and item[k].strip()
                for k in ("issue", "strategy", "evidence")) and
            type(item.get("progress")) is bool, "Attempt needs issue, strategy, evidence and progress")
    if decision == "CHANGE_STRATEGY":
        require(item["strategy"] not in {attempt["strategy"] for attempt in
                attempts[-plan["repair"]["no_progress_threshold"]:]}, "Choose a different strategy")
    require(not any(item["issue"] == old["issue"] and item["strategy"] == old["strategy"] and
                    item["evidence"] == old["evidence"] and not old["progress"] for old in attempts),
            "Repeated disproven strategy without new evidence")
    attempts.append({key: item[key] for key in ("issue", "strategy", "evidence", "progress")} |
                    {"recorded": now()})
    write(path, history)
    return policy(plan["repair"], attempts)


def discover(root):
    return {"project": str(root),
            "markers": {name: kind for name, kind in MARKERS.items() if (root / name).is_file()},
            "tools": {name: shutil.which(name) for name in
                      ("git", "python", "python3", "py", "php", "composer", "node", "npm",
                       "mariadb", "mysql")},
            "instructions": [str(path / "AGENTS.md") for path in (root, *root.parents)
                             if (path / "AGENTS.md").is_file()]}


def requirement_results(plan, rows, stable):
    checks = {row["id"]: row["status"] for row in rows}
    results = {}
    for ident, links in plan.get("requirements", {}).items():
        states = {checks[link] for link in links} if stable else {"NOT_RUN"}
        status = next(state for state in ("FAIL", "BLOCKED", "NOT_RUN", "PASS")
                      if state in states)
        results[ident] = {"checks": links, "status": status}
    return results


def finalize(report_path, root, plan, assessment_path, stamp):
    report = read(report_path) if report_path.exists() else {}
    data = read(assessment_path) if assessment_path else {}
    run_id = report.get("run_id")
    fingerprint_now = stamp()
    if not (run_id and report.get("stable") is True and report.get("project") == str(root)
            and report.get("plan") == plan
            and report.get("checked_fingerprint") == report.get("source_fingerprint") == fingerprint_now
            and isinstance(data, dict) and data.get("run_id") == run_id
            and assessment_matches(data, fingerprint_now, root)):
        print("BLOCKED: Final assessment must identify the current reviewed execution",
              file=sys.stderr)
        return 2
    review, issues = assessment(data, fingerprint_now, root)
    # A new review may add findings. Resolving a recorded finding requires a new run.
    prior_issues = {issue["id"]: issue for issue in report["issues"]}
    for issue in issues:
        prior = prior_issues.get(issue["id"])
        if (prior is None or prior["resolved"] or
                (is_blocker(issue, plan) and not is_blocker(prior, plan))):
            prior_issues[issue["id"]] = issue
    issues = list(prior_issues.values())
    for gate, previous in report["assessment"].items():
        if previous["status"] == "FAIL" or gate not in review:
            review[gate] = previous
    status, gates, blockers = evaluate(plan, report["checks"], review, issues, True)
    scope = git_scope(root, plan)
    if stamp() != fingerprint_now:
        print("BLOCKED: Source changed during finalization", file=sys.stderr)
        return 2
    report.setdefault("checked_git_scope", report.get("git_scope", {"status": "UNAVAILABLE"}))
    report.update(status=status, gates=gates, assessment=review, issues=issues, git_scope=scope,
                  blockers=blockers, completed=status == "PASS")
    write(report_path, report)
    print(json.dumps({"status": status, "report": str(report_path)}))
    return EXIT[status]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discover", "fingerprint", "run", "attempt", "finalize"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--assessment", type=Path)
    parser.add_argument("--entry", type=Path)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        require(root.is_dir(), "Project root must be a directory")
        if args.action == "discover":
            print(json.dumps(discover(root)))
            return 0
        require(args.plan is not None, "--plan is required")
        plan = config(args.plan)
        stamp = lambda: fingerprint(root, plan["source"], plan.get("exclude", []))
        if args.action == "fingerprint":
            print(stamp())
            return 0
        require(args.state is not None, "--state must name a dedicated task directory")
        state = args.state.resolve()
        require(not state.is_relative_to(root), "--state must be outside the project")
        with locked(state):
            history_path = state / "history.json"
            if args.action == "attempt":
                require(args.entry is not None, "--entry is required")
                print(add_attempt(history_path, plan, root, read(args.entry)))
                return 0
            history = read(history_path) if history_path.exists() else {"project": str(root), "attempts": []}
            require(history.get("project") == str(root), "History belongs to another project")
            report_path = state / "report.json"
            if args.action == "finalize":
                return finalize(report_path, root, plan, args.assessment, stamp)
            # Replace any old success before running a new check set.
            write(report_path, {"skill": SKILL, "schema_version": "1.0", "project": str(root),
                                "status": "BLOCKED", "reason": "Verification incomplete"})
            run_started_ns = time.time_ns()
            before = stamp()
            deadline = time.monotonic() + plan["limits"]["total_seconds"]
            with ThreadPoolExecutor(max_workers=plan["limits"]["workers"]) as pool:
                rows = list(pool.map(lambda check: execute(check, root, plan["limits"], deadline, state),
                                     plan.get("checks", [])))
            data = read(args.assessment) if args.assessment else {}
            review, issues = assessment(data, before, root)
            scope = git_scope(root, plan)
            try:
                after = stamp()
            except (ValueError, OSError):
                after = None
            stable = before == after and config(args.plan) == plan
            status, gates, blockers = evaluate(plan, rows, review, issues, stable)
            report = {"skill": SKILL, "schema_version": "1.0", "project": str(root),
                      "status": status, "level": plan["level"], "plan": plan, "source_fingerprint": after,
                      "run_id": uuid4().hex, "run_started_ns": run_started_ns, "stable": stable,
                      "requirements": requirement_results(plan, rows, stable), "git_scope": scope,
                      "checked_fingerprint": before, "required": plan["required"],
                      "gates": gates, "checks": rows, "assessment": review,
                      "issues": issues, "blockers": blockers, "completed": status == "PASS",
                      "repair_attempts": len(history["attempts"]),
                      "repair_policy": policy(plan["repair"], history["attempts"])}
            write(report_path, report)
            print(json.dumps({"status": status, "report": str(report_path)}))
            return EXIT[status]
    except FileExistsError:
        print("BLOCKED: task state is locked or already in use", file=sys.stderr)
        return 2
    except (ValueError, OSError, TypeError, KeyError) as error:
        print(f"Invalid or unavailable inputs ({type(error).__name__}): {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

