import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
from review_uncovered import source_line_diagnostic  # noqa: E402


class SourceLineDiagnosticTests(unittest.TestCase):
    def test_distinguishes_any_instance_from_all_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "merged.dat"
            raw.write_text(
                "# SystemC::Coverage-3\n"
                "C '\x01f\x02/hardware/src/test.sv\x01l\x021\x01t\x02line"
                "\x01h\x02TOP.tb.dut.lane0' 3\n"
                "C '\x01f\x02/hardware/src/test.sv\x01l\x021\x01t\x02line"
                "\x01h\x02TOP.tb.dut.lane1' 0\n"
                "C '\x01f\x02/hardware/src/test.sv\x01l\x022\x01t\x02line"
                "\x01h\x02TOP.tb.dut.lane0' 0\n"
                "C '\x01f\x02/hardware/src/test.sv\x01l\x023\x01t\x02expr"
                "\x01h\x02TOP.tb.dut.lane0' 1\n"
                "C '\x01f\x02/hardware/tb/test.sv\x01l\x024\x01t\x02line"
                "\x01h\x02TOP.tb.dut.lane0' 1\n"
            )
            result = source_line_diagnostic(raw, "tb.dut", ["/hardware/src/"])
        self.assertEqual(result["by_source"]["/hardware/src/test.sv"], {
            "lines_total": 2,
            "lines_any_hit": 1,
            "lines_all_instances_hit": 0,
        })


if __name__ == "__main__":
    unittest.main()
