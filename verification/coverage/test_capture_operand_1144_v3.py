import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_operand_1144_v3 as v3
import test_capture_operand_1144 as v1_tests
import test_capture_operand_1144_v2 as v2_tests


_prior_helper = None


def setUpModule():
    global _prior_helper
    _prior_helper = os.environ.get("OP1144_BASE_HOOK")
    os.environ["OP1144_BASE_HOOK"] = str(v3.v2.ORIGINAL_TCL)


def tearDownModule():
    if _prior_helper is None:
        os.environ.pop("OP1144_BASE_HOOK", None)
    else:
        os.environ["OP1144_BASE_HOOK"] = _prior_helper


class AbsoluteSourceTests(unittest.TestCase):
    def source_from_output(self, helper, emulate_dve=False):
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, OP1144_BASE_HOOK=str(helper))
            # Model the observed DVE relative info-script context, not Tclsh's
            # normally absolute source filename. The loader must ignore it.
            prefix = '''rename info real_info
proc info {args} {
    if {[lindex $args 0] eq "script"} {return capture_operand_1144_v3.tcl}
    return [uplevel 1 [linsert $args 0 real_info]]
}
''' if emulate_dve else ""
            script = prefix + '''set op1144_library_only 1
if {[catch {source {%s}} message]} {puts "GATE_REJECT $message"; exit 3}
op1144_v3_procs
puts ABSOLUTE_HELPERS_PASS
''' % v3.original.TCL
            return subprocess.run(["tclsh"], input=script, text=True, capture_output=True,
                                  cwd=directory, env=env)

    def test_absolute_source_from_unrelated_cwd_and_relative_info_script(self):
        for emulate in (False, True):
            result = self.source_from_output(v3.v2.ORIGINAL_TCL, emulate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("ABSOLUTE_HELPERS_PASS", result.stdout)

    def test_missing_relative_and_incomplete_helpers_fail_closed(self):
        for path in (Path("relative-helper.tcl"), Path("/missing/helper.tcl")):
            result = self.source_from_output(path)
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertNotIn("OP1144_WAITING_FOR_LIVE_IDENTITY", result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            incomplete = Path(directory) / "incomplete.tcl"
            incomplete.write_text("proc op1144_require {args} {}\n")
            result = self.source_from_output(incomplete)
            self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
            self.assertIn("Required helper proc missing", result.stdout)
            self.assertNotIn("OP1144_WAITING_FOR_LIVE_IDENTITY", result.stdout)


class V3CaptureTests(v1_tests.CaptureTests):
    def setUp(self):
        super().setUp()
        self.helper_environment = patch.dict(os.environ, OP1144_BASE_HOOK=str(v3.v2.ORIGINAL_TCL))
        self.helper_environment.start()
        self.addCleanup(self.helper_environment.stop)


class V3ScopeTests(v2_tests.ScopeTests):
    def setUp(self):
        self.helper_environment = patch.dict(os.environ, OP1144_BASE_HOOK=str(v3.v2.ORIGINAL_TCL))
        self.helper_environment.start()
        self.addCleanup(self.helper_environment.stop)


if __name__ == "__main__":
    unittest.main()
