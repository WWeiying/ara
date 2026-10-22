"""Offline negative gates; never invokes VCS."""
import copy
import json
from pathlib import Path
import unittest
import run_gap83_old_image as r


class GateTests(unittest.TestCase):
    def test_exact262_signature(self):
        r.signature({0x1000:1,0x2000:262,0x2004:0},0x1000,0x2000)
        for writes in ({0x1000:1,0x2000:261,0x2004:0},
                       {0x1000:1,0x2000:262,0x2004:1},
                       {0x1000:3,0x2000:262,0x2004:0},
                       {0x1000:1,0x2000:262}):
            with self.assertRaises(ValueError):r.signature(writes,0x1000,0x2000)

    def test_exact3_retained_targets(self):
        inventory = json.loads(r.RETAINED.read_text())
        self.assertEqual(len(r.targets(inventory)),3)
        bad = copy.deepcopy(inventory)
        bad["retained"] += [copy.deepcopy(next(x for x in bad["retained"] if not x["hit"] and x["point"]["line"] == "93"))]
        with self.assertRaises(ValueError):r.targets(bad)

    def test_oracle_bits_exact_and_not_tolerance(self):
        import struct
        self.assertEqual(struct.unpack("<I",struct.pack("<f",32*2**-24))[0],0x36000000)
        self.assertEqual(struct.unpack("<I",struct.pack("<f",64*2**-24))[0],0x36800000)
        source = r.SOURCE.read_text()
        self.assertIn('"=&r"(vl)',source)
        self.assertIn("output[i] != expected",source)
        self.assertNotIn("fabs",source)

    def test_missing_digest_prevents_launch(self):
        with self.assertRaises(ValueError):r.run(Path("/nonexistent"),None)


if __name__ == "__main__":unittest.main()
