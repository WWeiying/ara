import struct
import unittest
from capture_metadata_core import global_file_offset


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.header = bytearray(4096)
        self.header[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<HH', self.header, 16, 4, 243)
        struct.pack_into('<Q', self.header, 32, 64)
        struct.pack_into('<HH', self.header, 54, 56, 1)
        struct.pack_into('<IIQQQQQQ', self.header, 64, 1, 6, 0x2000,
                         0x3f00022000, 0, 4096, 4096, 4096)

    def test_address_translation_uses_file_offset(self):
        self.assertEqual(global_file_offset(self.header, 0x3f00022ca0, 32), 0x2ca0)

    def test_missing_core_bytes_are_not_zero_data(self):
        struct.pack_into('<Q', self.header, 64+32, 0)
        with self.assertRaises(ValueError):
            global_file_offset(self.header, 0x3f00022ca0, 32)

    def test_wrong_elf_type(self):
        struct.pack_into('<H', self.header, 16, 3)
        with self.assertRaises(ValueError):
            global_file_offset(self.header, 0x3f00022ca0, 32)

    def test_truncated_program_header_table(self):
        struct.pack_into('<H', self.header, 56, 1000)
        with self.assertRaises(ValueError):
            global_file_offset(self.header, 0x3f00022ca0, 32)


if __name__ == '__main__':
    unittest.main()
