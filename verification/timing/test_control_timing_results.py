import csv
from pathlib import Path
import tempfile
import unittest

from .collect_control_timing_results import compare_commands, compare_real, completed


class ControlTimingResultsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.before = Path(self.temp.name) / "before"
        self.after = Path(self.temp.name) / "after"

    def command_text(self):
        return "".join(
            f"QBS end-to-end case {i} PASS profile=1 M=4 N=7 Kb=2 layouts=2/2 cycles=876\n"
            for i in range(33))

    def write_rows(self, path, count=6, cycle="7304"):
        with path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(("case", "cycles", "weight_bytes"))
            writer.writerows((f"case{i}", cycle, "27648") for i in range(count))

    def test_commands_equal(self):
        self.before.write_text(self.command_text())
        self.after.write_text(self.command_text())
        self.assertEqual(len(compare_commands(self.before, self.after)), 33)

    def test_command_cycle_change_rejected(self):
        self.before.write_text(self.command_text())
        self.after.write_text(self.command_text().replace("cycles=876", "cycles=877", 1))
        with self.assertRaises(RuntimeError):
            compare_commands(self.before, self.after)

    def test_repeated_commands_rejected(self):
        self.before.write_text(self.command_text())
        self.after.write_text(self.command_text() * 2)
        with self.assertRaises(RuntimeError):
            compare_commands(self.before, self.after)

    def test_real_equal(self):
        self.write_rows(self.before)
        self.write_rows(self.after)
        self.assertEqual(len(compare_real(self.before, self.after)), 6)

    def test_missing_real_rejected(self):
        self.write_rows(self.before)
        self.write_rows(self.after, count=5)
        with self.assertRaises(RuntimeError):
            compare_real(self.before, self.after)

    def test_real_cycle_change_rejected(self):
        self.write_rows(self.before)
        self.write_rows(self.after, cycle="7305")
        with self.assertRaises(RuntimeError):
            compare_real(self.before, self.after)

    def test_late_failure_rejected(self):
        self.after.write_text("PASS\n$finish\nFatal: late failure\n")
        with self.assertRaises(RuntimeError):
            completed(self.after, "PASS")


if __name__ == "__main__":
    unittest.main()
