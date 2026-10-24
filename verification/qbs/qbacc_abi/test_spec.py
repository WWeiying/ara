"""Mutation checks for reserved QBACC fields; never writes the production spec."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
module_spec = importlib.util.spec_from_file_location("qbs_abi_generator", ROOT / "scripts/gen_qbs_abi.py")
gen = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(gen)


class SpecTests(unittest.TestCase):
    def test_current(self):
        gen.validate_spec(gen.load_spec())

    def test_accumulate_bit(self):
        for bit in (-1, 0, 1, 2, 4, 5, 6, 7, 32, True, 3.0, "3", None):
            with self.subTest(bit=bit):
                spec = copy.deepcopy(gen.load_spec())
                spec["instruction"]["qbacc_funct7_bit"] = bit
                with self.assertRaises(ValueError):
                    gen.validate_spec(spec)

    def test_overlap(self):
        spec = copy.deepcopy(gen.load_spec())
        spec["instruction"]["m_minus_one_bits"] = 4
        with self.assertRaisesRegex(ValueError, "overlaps"):
            gen.validate_spec(spec)

    def test_m_field(self):
        for bits in (0, 1, 2, 5, 6, True, 3.0, "3"):
            with self.subTest(bits=bits):
                spec = copy.deepcopy(gen.load_spec())
                spec["instruction"]["m_minus_one_bits"] = bits
                with self.assertRaises(ValueError):
                    gen.validate_spec(spec)

    def test_capability_reservations(self):
        for key in ("capability_index", "capability_bit", "vlen_bits"):
            for value in (-1, 1, 3, 32, True, "4", None):
                with self.subTest(key=key, value=value):
                    spec = copy.deepcopy(gen.load_spec())
                    spec["vrf_continuation"][key] = value
                    with self.assertRaises(ValueError):
                        gen.validate_spec(spec)


if __name__ == "__main__":
    unittest.main()
