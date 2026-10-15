#!/usr/bin/env python3
"""Launch the same38 with complete failure veto and fail-stop exceptions."""
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import replay_candidate04_regression_successor as reviewed

original = reviewed.original
base = reviewed.base
PREPARE = original.prepare
WORK = original.work
SELF_TEST = original.self_test
reviewed.BAD = re.compile(reviewed.BAD.pattern +
                          r"|\b(?:MATRIX_FAIL|EXTENSION_MATRIX_FAIL|EXTENDED_FAIL|EPOCH_FAIL)\b")


def runner_class(parent, entries):
    checked = reviewed.strict_runner(parent, entries)

    class Runner(checked):
        def _run_test(self, test, image):
            try:
                return super()._run_test(test, image)
            except BaseException:
                self.cancel_event.set()
                raise
    return Runner


def prepare(out):
    PREPARE(out)
    data = base.read(out / "plan.json")
    path = Path(__file__).resolve()
    data["pins"][str(path)] = base.sha(path)
    data["final_checker"] = "Matrix failure veto and fail-stop on checker exceptions"
    base.save(out / "plan.json", data)
    preflight = base.read(out / "preflight.json")
    preflight["plan_sha256"] = base.sha(out / "plan.json")
    preflight["final_checker_pinned"] = True
    base.save(out / "preflight.json", preflight)
    base.verify_pins(data["pins"])
    print("FINAL_READY_NOT_LAUNCHED " + preflight["plan_sha256"], flush=True)


def work(out, approved, authorized):
    base.require(authorized and approved == base.sha(out / "plan.json"), "Unapproved launch")
    path = Path(__file__).resolve()
    base.require(base.read(out / "plan.json")["pins"].get(str(path)) == base.sha(path),
                 "Final checker not pinned")
    return WORK(out, approved, authorized)


def self_test():
    import threading
    import unittest
    from unittest.mock import patch
    SELF_TEST()

    class Tests(unittest.TestCase):
        def test_matrix_failure_veto(self):
            good = "Core Test *** SUCCESS *** (tohost = 0)\n$finish\n"
            for marker in ("MATRIX_FAIL", "EXTENSION_MATRIX_FAIL", "EXTENDED_FAIL", "EPOCH_FAIL"):
                self.assertFalse(reviewed.strict_console(good + marker))

        def test_checker_exception_stops_dispatch(self):
            class Broken:
                def _run_test(self, test, image):
                    raise OSError("test missing console")
            with patch.object(reviewed, "strict_runner", return_value=Broken):
                runner = runner_class(None, [])()
                runner.cancel_event = threading.Event()
                with self.assertRaises(OSError):
                    runner._run_test(None, None)
                self.assertTrue(runner.cancel_event.is_set())

    base.require(unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
                 .wasSuccessful(), "Final checker tests failed")


original.prepare = prepare
original.work = work
original.self_test = self_test
base.runner_class = runner_class

if __name__ == "__main__":
    raise SystemExit(original.main())
