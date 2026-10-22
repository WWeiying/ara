import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


COVERAGE = Path(__file__).resolve().parents[1] / "coverage"
sys.path.insert(0, str(COVERAGE))
SPEC = importlib.util.spec_from_file_location(
    "review_toggle_signals", COVERAGE / "review_toggle_signals.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ToggleReviewTest(unittest.TestCase):
    def test_groups_bits_and_filters_hierarchy_source_and_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "merged.dat"

            def point(source, instance, name, count):
                fields = {"f": source, "h": instance, "o": name, "t": "toggle"}
                payload = "\x01".join(f"{key}\x02{value}" for key, value in fields.items())
                return f"C '{payload}' {count}\n"

            raw.write_text("".join([
                point("/hardware/src/ara_dispatcher.sv", "TOP.tb.dut.dispatcher",
                      "ready[0]", 2),
                point("/hardware/src/ara_dispatcher.sv", "TOP.tb.dut.dispatcher",
                      "ready[1]", 0),
                point("/hardware/src/ara_dispatcher.sv", "TOP.tb.dut.dispatcher",
                      "data[0]", 4),
                point("/hardware/tb/ara_tb.sv", "TOP.tb.dut.testbench", "ready[0]", 1),
                point("/hardware/src/ara_dispatcher.sv", "TOP.tb.other", "ready[0]", 1),
            ]))
            summary = MODULE.summarize(raw, "tb.dut", ["/hardware/src/"], ["ready"])
            self.assertEqual(summary["signals_total"], 1)
            self.assertEqual(summary["signal_bits_total"], 2)
            self.assertEqual(summary["signal_bits_toggled"], 1)
            self.assertEqual(summary["signals"][0]["signal"], "ready")
            self.assertEqual(summary["signals"][0]["transition_count"], 2)


if __name__ == "__main__":
    unittest.main()
