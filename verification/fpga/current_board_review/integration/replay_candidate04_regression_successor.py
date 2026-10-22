#!/usr/bin/env python3
"""Reviewed work-path successor; preserve the initial unlaunched draft."""
import copy
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import replay_candidate04_regression as original

base = original.base
OLD_GATES = original.gates
OLD_PREPARE = original.prepare
OLD_WORK = original.work
OLD_SELF_TEST = original.self_test
OLD_RUNNER = base.runner_class
BAD = re.compile(r"\bRVV_[A-Z0-9_]*FAIL\b|BOARD_CASE_FAIL|"
                 r"BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL|VLEN_FAIL)|"
                 r"Core Test \*\*\* FAIL|Error-\[|Fatal[-:]|UVM_FATAL")


def strict_console(text):
    return ("Core Test *** SUCCESS *** (tohost = 0)" in text and
            "$finish" in text and "SKIP" not in text and not BAD.search(text))


def gates(previous, terminal, audit, floating):
    OLD_GATES(previous, terminal, audit, floating)
    rows = floating.get("results", [])
    base.require(len(rows) == 3 and {x["name"] for x in rows} ==
                 {"vv_restart16", "vv_start0", "vf_restart16"}, "FP3 membership missing")
    base.require(all(x["status"] == x["runner_status"] == "PASS" and
                     x["runner_returncode"] == x["sim_returncode"] == 0 and
                     x["failure_marker_veto"] is False for x in rows), "FP3 detail not PASS")
    base.require(all(floating.get(k) is True for k in
                     ("all_pass", "same_elf", "same_checker", "pins_unchanged")), "FP3 identity gate missing")


def strict_runner(parent, entries):
    checked = OLD_RUNNER(parent, entries)

    class Runner(checked):
        def _run_test(self, test, image):
            result = super()._run_test(test, image)
            if result.status == "PASS":
                text = (result.artifact_dir / "console.log").read_text()
                if result.returncode != 0 or not strict_console(text):
                    result.status = "FAIL"
                    result.reason = "raw failure/incomplete exit veto"
                    self.cancel_event.set()
            return result
    return Runner


def prepare(out):
    OLD_PREPARE(out)
    data = base.read(out / "plan.json")
    data["pins"][str(Path(__file__).resolve())] = base.sha(Path(__file__).resolve())
    data["work_successor"] = "Create admission directory; strict FP3 detail and raw console gates"
    base.save(out / "plan.json", data)
    preflight = base.read(out / "preflight.json")
    preflight["plan_sha256"] = base.sha(out / "plan.json")
    preflight["successor_pinned"] = True
    base.save(out / "preflight.json", preflight)
    base.verify_pins(data["pins"])
    print("SUCCESSOR_READY_NOT_LAUNCHED " + preflight["plan_sha256"], flush=True)


def admission_directory(out):
    directory = out / "admission"
    directory.mkdir(exist_ok=False)
    return directory


def work(out, approved, authorized):
    base.require(authorized and approved == base.sha(out / "plan.json"), "Unapproved launch")
    base.require(not (out / "launch.json").exists(), "Already launched; no retry")
    data = base.read(out / "plan.json")
    key = str(Path(__file__).resolve())
    base.require(data["pins"].get(key) == base.sha(Path(key)), "Successor not pinned")
    base.verify_pins(data["pins"])
    admission_directory(out)
    return OLD_WORK(out, approved, authorized)


def self_test():
    import tempfile
    import unittest
    OLD_SELF_TEST()

    class Tests(unittest.TestCase):
        def test_admission_parent_before_workers(self):
            with tempfile.TemporaryDirectory() as root:
                out = Path(root)
                directory = admission_directory(out)
                base.save(directory / "example.json", {"accepted": True})
                self.assertTrue(base.read(directory / "example.json")["accepted"])
                with self.assertRaises(FileExistsError):
                    admission_directory(out)

        def test_fp3_empty_and_bad_details_rejected(self):
            previous = base.read(original.PREVIOUS / "plan.json")
            terminal = base.read(original.PREVIOUS / "complete.json")
            audit, floating = base.read(original.AUDIT), base.read(original.FP)
            for value in ([], [dict(x, sim_returncode=1) for x in floating["results"]]):
                bad = copy.deepcopy(floating)
                bad["results"] = value
                with self.assertRaises(ValueError):
                    gates(previous, terminal, audit, bad)

        def test_contradictory_or_incomplete_success_rejected(self):
            good = "Core Test *** SUCCESS *** (tohost = 0)\n$finish\n"
            self.assertTrue(strict_console(good))
            for value in ("RVV_MASK_FAIL", "RVV_EXTENSION_FAIL", "RVV_FP_COMPARE_FAIL",
                          "BOARD_CASE_FAIL", "BOARD_REPLAY_TRAP", "Fatal: fixture", "SKIP"):
                self.assertFalse(strict_console(good + value))
            self.assertFalse(strict_console("Core Test *** SUCCESS *** (tohost = 0)"))
            for case in base.read(original.PREVIOUS / "plan.json")["cases"]:
                console = original.PREVIOUS / "replay/tests" / case["id"] / "console.log"
                self.assertTrue(strict_console(console.read_text()), case["id"])

    base.require(unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
                 .wasSuccessful(), "Successor work-path tests failed")


original.gates = gates
original.prepare = prepare
original.work = work
original.self_test = self_test
base.runner_class = strict_runner

if __name__ == "__main__":
    raise SystemExit(original.main())
