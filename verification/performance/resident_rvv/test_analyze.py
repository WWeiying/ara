import unittest
from analyze import helper_ranges, retirement_spans, HELPERS


def row(cycle, pc, insn="00000013", value="0"):
    return dict(cycle=str(cycle), pc=f"{pc:x}", insn=insn, rd_wdata=value, event="retire")


class TraceTests(unittest.TestCase):
    def test_ranges(self):
        text = f"00000100 <{HELPERS[0]}>:\n00000200 <{HELPERS[1]}>:\n00000300 <after>:\n"
        self.assertEqual(helper_ranges(text)[HELPERS[1]], (512, 768))

    def test_spans_and_offset(self):
        rows = [row(11, 0, "c0002573", "a"), row(12, 256), row(20, 260),
                row(25, 0), row(31, 0, "c0002573", "1e")]
        spans, markers = retirement_spans(rows, {"helper": (256, 512)}, {10, 30})
        self.assertEqual(markers, {10: 11, 30: 31})
        self.assertEqual((spans[0]["begin"], spans[0]["end"], spans[0]["retired"]), (12, 25, 2))

    def test_reject_incomplete(self):
        with self.assertRaises(ValueError):
            retirement_spans([], {}, {10})

    def test_reject_variable_offset(self):
        with self.assertRaises(ValueError):
            retirement_spans([row(11, 0, "c0002573", "a"),
                              row(32, 0, "c0002573", "1e")], {}, {10, 30})


if __name__ == "__main__":
    unittest.main()
