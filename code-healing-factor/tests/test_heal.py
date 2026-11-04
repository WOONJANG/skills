import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import heal
from stop_hook import respond

CORRECT = "def total(n):\n    return n * 2\n"
ORACLE = "from app import total\nassert total(7) == 14\nassert total(0) == 0\nassert total(-1) == -2\n"
PYTHON = "{python}"


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.root = base / "한글 project"
        self.root.mkdir()
        self.state = base / "evidence"
        self.plan_file = base / "plan.json"
        self.review_file = base / "review.json"
        self.entry = base / "attempt.json"
        self.source = self.root / "app.py"
        self.source.write_text(CORRECT, encoding="utf-8")
        (self.root / "검증 test.py").write_text(ORACLE, encoding="utf-8")
        self.plan = {"schema_version": "1.0", "source": ["."], "level": "LIGHT",
                     "required": ["G04", "G06", "G11"],
                     "checks": [
                         {"id": "syntax", "gate": "G04", "argv": [PYTHON, "-m", "py_compile", "app.py"]},
                         {"id": "behavior", "gate": "G06", "argv": [PYTHON, "검증 test.py"]},
                         {"id": "regression", "gate": "G11", "argv": [PYTHON, "-c",
                          "from app import total; assert total(-1) == -2"]}]}

    def cli(self, action="run", expected=0, review=True):
        heal.write(self.plan_file, self.plan)
        if review:
            heal.write(self.review_file, {"project": str(self.root),
                        "fingerprint": heal.fingerprint(self.root, self.plan["source"]),
                        "gates": {"G01": {"status": "PASS", "reason": "Doubling contract mapped to fixture"},
                                  "G14": {"status": "PASS", "reason": "Oracle reviewed independently"}}})
        result = subprocess.run([sys.executable, str(SCRIPTS / "heal.py"), action,
                                 "--root", str(self.root), "--state", str(self.state),
                                 "--plan", str(self.plan_file), "--assessment", str(self.review_file),
                                 "--entry", str(self.entry)], capture_output=True, text=True,
                                encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return heal.read(self.state / "report.json") if action == "run" and expected != 3 else result.stdout

    def test_valid_unchanged(self):
        report = self.cli()
        self.assertTrue(report["completed"])
        self.assertEqual(self.source.read_text(), CORRECT)
        self.assertEqual(len(report["checks"]), 3)

    def test_mutations_and_repair(self):
        for defect, gate in [("def total(n)\n    return n * 2\n", "G04"),
                             (CORRECT.replace("* 2", "* 3"), "G06"),
                             (CORRECT.replace("n * 2", "2 / n"), "G06"),
                             (CORRECT.replace("n * 2", "abs(n) * 2"), "G11")]:
            with self.subTest(gate=gate, defect=defect):
                self.source.write_text(defect)
                self.assertEqual(self.cli(expected=1)["gates"][gate], "FAIL")
                self.source.write_text(CORRECT)
                self.assertEqual(self.cli()["status"], "PASS")

    def test_missing_execution_and_review(self):
        self.plan["checks"].pop()
        self.assertEqual(self.cli(expected=2)["gates"]["G11"], "NOT_RUN")
        assessment = heal.read(self.review_file)
        assessment["gates"]["G11"] = {"status": "PASS", "reason": "Fabricated"}
        heal.write(self.review_file, assessment)
        self.cli(expected=3, review=False)

    def test_successful_command_cannot_replace_requirements_review(self):
        self.cli()
        assessment = heal.read(self.review_file)
        del assessment["gates"]["G01"]
        heal.write(self.review_file, assessment)
        self.plan["checks"].append({"id": "noop", "gate": "G01", "argv": [PYTHON, "-c", "pass"]})
        self.assertEqual(self.cli(expected=2, review=False)["gates"]["G01"], "NOT_RUN")

    def test_source_changes_invalidate_evidence(self):
        self.cli()
        self.source.write_text(CORRECT + "# user edit\n")
        self.assertEqual(self.cli(expected=2, review=False)["gates"]["G01"], "NOT_RUN")
        self.cli()
        self.plan["checks"].append({"id": "writer", "gate": "G08", "argv": [
            PYTHON, "-c", "from pathlib import Path; Path('app.py').write_text('# changed')"]})
        report = self.cli(expected=2)
        self.assertNotEqual(report["source_fingerprint"], report["checked_fingerprint"])

    def test_timeout_and_missing_executable(self):
        self.plan["checks"] += [
            {"id": "timeout", "gate": "G07", "timeout": 1,
             "argv": [PYTHON, "-c", "import time; time.sleep(10)"]},
            {"id": "missing", "gate": "G07", "argv": ["no-such-executable-248659"]}]
        self.plan["required"].append("G07")
        report = self.cli(expected=2)
        self.assertEqual([row["reason"] for row in report["checks"][-2:]],
                         ["Command timeout", "Executable unavailable"])

    def test_output_oracle_and_no_raw_output(self):
        expected = hashlib.sha256(b"expected").hexdigest()
        self.plan["checks"].append({"id": "oracle", "gate": "G08", "stdout_sha256": expected,
                                    "argv": [PYTHON, "-c", "print('different', end='')"]})
        self.assertEqual(self.cli(expected=1)["checks"][-1]["reason"], "Stdout digest mismatch")
        self.plan["checks"][-1]["argv"][-1] = "print('expected', end='')"
        self.assertEqual(self.cli()["checks"][-1]["exit_code"], 0)
        self.plan["required"].append("G08")
        self.plan["limits"] = {"stdout_bytes": 4}
        self.assertEqual(self.cli(expected=2)["checks"][-1]["status"], "BLOCKED")

    def test_retry_pivot_and_limit(self):
        self.plan["repair"] = {"max_iterations": 3}
        for index, strategy in enumerate(("inspect", "minimize", "isolate")):
            heal.write(self.entry, {"issue": "CHF-1", "strategy": strategy,
                                    "evidence": f"environment remains unavailable {index}", "progress": False})
            if index == 2:
                entry = heal.read(self.entry)
                heal.write(self.entry, entry | {"strategy": "inspect"})
                self.cli("attempt", expected=3)
                heal.write(self.entry, entry)
            result = self.cli("attempt")
        self.assertIn("STOP_LIMIT", result)
        self.cli("attempt", expected=3)

    @unittest.skipUnless(shutil.which("git"), "git unavailable")
    def test_dirty_git_preserved(self):
        def git(*args):
            return subprocess.check_output(["git", *args], cwd=self.root)
        git("init", "-q")
        git("add", "app.py")
        self.source.write_text(CORRECT + "# existing edit\n")
        before = git("status", "--porcelain", "--untracked-files=all")
        self.cli()
        # Compilation creates only ignored-for-comparison Python caches.
        after = git("status", "--porcelain", "--untracked-files=all")
        self.assertEqual(before, b"\n".join(line for line in after.splitlines()
                                            if b"__pycache__" not in line) + b"\n")
        self.assertIn("# existing edit", self.source.read_text())

    def test_security_threshold_and_incomplete_review(self):
        self.cli()
        review = heal.read(self.review_file)
        review["issues"] = [{"id": "CHF-1", "category": "SECURITY_VULNERABILITY",
                             "severity": "HIGH", "location": "fixture",
                             "evidence": "isolated review finding", "blocking": False, "resolved": False}]
        heal.write(self.review_file, review)
        self.assertEqual(self.cli(expected=1, review=False)["blockers"], ["CHF-1"])
        review["issues"].clear()
        del review["gates"]["G14"]
        heal.write(self.review_file, review)
        self.assertEqual(self.cli(expected=2, review=False)["gates"]["G14"], "NOT_RUN")

    def test_stop_lifecycle(self):
        self.state.mkdir()
        event = {"hook_event_name": "Stop", "session_id": "session", "turn_id": "turn",
                 "cwd": str(self.root), "stop_hook_active": False}
        heal.write(self.state / "arm.json", {"session_id": "session", "turn_id": "turn", "cancelled": False})
        heal.write(self.plan_file, self.plan)
        call = lambda data=event: respond(data, self.root, self.plan_file, self.state)
        self.assertEqual(call()["decision"], "block")
        self.assertNotIn("decision", call(event | {"stop_hook_active": True}))
        self.assertEqual(call(event | {"turn_id": "another"}), {})
        self.cli()
        self.assertEqual(call(), {})
        self.source.write_text(CORRECT + "# stale\n")
        self.assertEqual(call()["decision"], "block")
        heal.write(self.state / "arm.json", {"session_id": "session", "turn_id": "turn", "cancelled": True})
        self.assertEqual(call(), {})


if __name__ == "__main__":
    unittest.main()
