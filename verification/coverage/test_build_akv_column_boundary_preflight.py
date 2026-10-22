"""Focused negative tests; software reference is not native custom execution."""
import unittest
from types import SimpleNamespace
import build_akv_column_boundary_preflight as b


class BoundaryTest(unittest.TestCase):
    def test_full_snapshots(self):
        values = b.expected_snapshots()
        self.assertEqual(len(values), 8192)
        self.assertEqual(values[:64], list(range(0x1000, 0x1040)))
        for p in range(4):
            start = p*2048 + 8*64
            self.assertEqual(values[start:start+64], [0x343f] + [0]*63)
        self.assertEqual(values[:2048], values[2048:4096])

    def test_complete_destination_and_guard_changes_detectable(self):
        values = b.expected_snapshots()
        for index in (8*64, 8*64+63, 7*64, 31*64+63, 4096+8*64):
            changed = list(values)
            changed[index] ^= 1
            self.assertNotEqual(changed, values)

    def test_instruction_encoding(self):
        word = 0x0005745b
        self.assertEqual((word & 127, word >> 25, (word >> 12) & 7,
                          (word >> 7) & 31, (word >> 15) & 31, (word >> 20) & 31),
                         (0x5b, 0, 7, 8, 10, 0))
        self.assertEqual((0x00b5605b >> 20) & 31, 11)

    def test_scalar_store_bytes(self):
        c = SimpleNamespace(instruction=0x1023, memory_accesses=[(0x100, 0x1234)])
        self.assertEqual(b.memory([c]), {0x100: 0x34, 0x101: 0x12})

    def test_reject_non_scalar_write(self):
        c = SimpleNamespace(instruction=0x1027, memory_accesses=[(0x100, 1)])
        with self.assertRaises(ValueError):
            b.memory([c])

    def test_reject_wrong_store_width(self):
        c = SimpleNamespace(instruction=0x4023, memory_accesses=[(0x100, 1)])
        with self.assertRaises(ValueError):
            b.memory([c])

    def test_reject_empty_trace(self):
        with self.assertRaises(ValueError):
            b.validate([], {})

    def test_reject_wrong_elf(self):
        with self.assertRaises(ValueError):
            b.native_elf_audit(b"wrong", {})


if __name__ == "__main__":
    unittest.main()
