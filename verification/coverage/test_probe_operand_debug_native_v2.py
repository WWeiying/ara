from pathlib import Path
import unittest


class BoundTests(unittest.TestCase):
    def test_no_exclusion_and_stop_at_first_unknown(self):
        text = Path(__file__).with_name("probe_operand_debug_native_v2.tcl").read_text()
        self.assertNotIn("gui_exclude_items", text)
        self.assertNotIn("gui_list_select", text)
        self.assertIn("$leaves > 4000", text)
        self.assertIn("$p < 1000", text)
        self.assertIn("DBG_FIRST_UNKNOWN", text)
        self.assertIn("probe_row $stream $metric $child 1\n                return", text)
        self.assertIn("gui_list_action -id CovDetail.1 Block", text)


if __name__ == "__main__":
    unittest.main()
