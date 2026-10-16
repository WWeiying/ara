import unittest
from audit_stall_ltx import audit


def fixture(pins):
    return {"ltx_root": {"ltx_data": [{"debug_cores": [{"name": "i_stall_ila", "pins": pins}]}]}}


class LtxTests(unittest.TestCase):
    def pins(self):
        return [dict(portIndex=0, leftIndex=0, rightIndex=1,
                     nets=[dict(isBus=True, subnets=[dict(name="v[1]"), dict(name="v[0]")])])]

    def test_bus_direction(self):
        result = audit(dict(physical_nets=["v[0]", "v[1]"]), fixture(self.pins()))
        self.assertTrue(result["exact_name_match"])
        self.assertFalse(result["routed_connectivity_proven"])

    def test_alias_does_not_silently_pass(self):
        result = audit(dict(physical_nets=["alias", "v[1]"]), fixture(self.pins()))
        self.assertEqual(result["mismatches"], [dict(bit=0, expected="alias", actual="v[0]")])

    def test_missing_and_overlapping_bits(self):
        with self.assertRaises(ValueError):
            audit(dict(physical_nets=["v[0]"]), fixture(self.pins()))
        with self.assertRaises(ValueError):
            audit(dict(physical_nets=["v[0]", "v[1]"]), fixture(self.pins()*2))


if __name__ == "__main__":
    unittest.main()
