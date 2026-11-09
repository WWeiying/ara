import unittest
import extract_real as e


class ExtractTest(unittest.TestCase):
    def rows(self):
        return [dict(lane="0", addr=str(8+i), be="ff", vd="2", eew="1", vl="128",
                     vstart="0", wdata=f"{i:016x}") for i in range(8)]

    def test_word_order(self):
        self.assertEqual(e.lane_words(list(reversed(self.rows())), 0, 2)[::4], list(range(8)))

    def test_reject_duplicate_address(self):
        rows = self.rows()
        rows[-1]["addr"] = rows[0]["addr"]
        with self.assertRaises(ValueError):
            e.lane_words(rows, 0, 2)

    def test_reject_partial_or_missing_word(self):
        rows = self.rows()
        rows[0]["be"] = "7f"
        with self.assertRaises(ValueError):
            e.lane_words(rows, 0, 2)
        with self.assertRaises(ValueError):
            e.lane_words(self.rows()[:-1], 0, 2)


if __name__ == "__main__":
    unittest.main()
