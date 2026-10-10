import unittest
from admit_gap83_offline import check_signature


class SignatureTests(unittest.TestCase):
    def test_real_bus_masks(self):
        check_signature({0x80002208: (0x0f, 262), 0x8000220c: (0xf0, 0)})

    def test_wrong_count(self):
        with self.assertRaises(ValueError):
            check_signature({0x80002208: (0x0f, 261), 0x8000220c: (0xf0, 0)})

    def test_failed_oracle(self):
        with self.assertRaises(ValueError):
            check_signature({0x80002208: (0x0f, 262), 0x8000220c: (0xf0, 1)})

    def test_missing_signature(self):
        with self.assertRaises(ValueError):
            check_signature({})

    def test_wrong_byte_mask(self):
        with self.assertRaises(ValueError):
            check_signature({0x80002208: (0x0f, 262), 0x8000220c: (0x0f, 0)})

    def test_wrong_address(self):
        with self.assertRaises(ValueError):
            check_signature({0x80002208: (0x0f, 262), 0x80002210: (0xf0, 0)})


if __name__ == '__main__':
    unittest.main()
