import unittest
from unittest.mock import patch

from compare_stall_reset import compare, read_inventory


INVENTORY = """MATCH root* COUNT 1
CELL {root/reg[0]} DEPTH 0 REF FDRE
PROPERTY {root/reg[0]} INIT 1'b0
INPUT {root/reg[0]/D} DRIVERS {{driver/reg[0]/Q}}
TOTAL_CELLS 1
"""


class ResetComparisonTest(unittest.TestCase):
    def parse(self, text):
        with patch("pathlib.Path.read_text", return_value=text):
            return read_inventory("unused")

    def test_identity_does_not_claim_equivalence(self):
        records = self.parse(INVENTORY)
        result = compare(records, records)
        self.assertTrue(result["identical_inventory"])
        self.assertFalse(result["equivalence_proven"])

    def test_depth_is_not_connectivity(self):
        self.assertEqual(self.parse(INVENTORY), self.parse(INVENTORY.replace("DEPTH 0", "DEPTH 2")))

    def test_changed_driver_and_init_detected(self):
        changed = INVENTORY.replace("driver/reg[0]", "other/reg[0]").replace("1'b0", "1'b1")
        result = compare(self.parse(INVENTORY), self.parse(changed))
        self.assertEqual(len(result["differences"]), 2)
        self.assertFalse(result["identical_inventory"])

    def test_missing_inventory_record_detected(self):
        records = self.parse(INVENTORY)
        other = dict(records)
        del other[("INPUT", "root/reg[0]/D")]
        self.assertEqual(len(compare(records, other)["differences"]), 1)

    def test_incomplete_or_duplicate_rejected(self):
        for text in (INVENTORY.replace("TOTAL_CELLS 1", ""),
                     INVENTORY.replace("TOTAL_CELLS 1", "TOTAL_CELLS 2"),
                     INVENTORY + "TOTAL_CELLS 1\n",
                     INVENTORY + "CELL x DEPTH 0 REF LUT1\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.parse(text)


if __name__ == "__main__":
    unittest.main()
