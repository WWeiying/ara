from pathlib import Path
import subprocess
import unittest


class AbsoluteHelperTests(unittest.TestCase):
    def test_absolute_helper_from_foreign_cwd(self):
        here = Path(__file__).resolve().parent
        text = (here / "probe_operand_debug_native_v3.tcl").read_text()
        self.assertNotIn("[info script]", text)
        self.assertIn("source {" + str(here / "probe_operand_debug_native.tcl") + "}", text)
        self.assertNotIn("gui_exclude_items", text)
        # Remove the actual session launch while exercising the real source/rename gate.
        prelude = text.split("if {[catch {probe_session}", 1)[0]
        result = subprocess.run(["tclsh"], cwd="/tmp", input=prelude +
            '\nif {[llength [info commands probe_initial_tree]] != 1} {error missing}\nputs PASS\n',
            text=True, capture_output=True, timeout=10)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.returncode, 0)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
