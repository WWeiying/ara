"""Offline oracle checks; no simulator invocation."""
import unittest

from build_masklogical_restart8 import expected, check_dump, PASS_LINE


class RestartEightTests(unittest.TestCase):
    def dump(self):
        return '\n'.join([f'RESTART8 {i} {expected(i).hex()}' for i in range(8)] + [PASS_LINE])

    def test_truth_tables_and_prefix(self):
        for op in range(8):
            row = expected(op)
            self.assertEqual(row[:8] + row[136:], b'\xd3' * 16)
            for bit in range(1024):
                byte, shift = divmod(bit, 8)
                x = ((0xc3 ^ byte * 29) >> shift) & 1
                y = ((0x69 ^ byte * 13) >> shift) & 1
                truth = (x and y, not (x and y), x and not y, x or y,
                         not (x or y), x or not y, x != y, x == y)[op]
                if bit < 256:
                    truth = (((0x69 ^ byte * 13) if op == 3 else (0xa5 ^ byte * 7)) >> shift) & 1
                self.assertEqual((row[8+byte] >> shift) & 1, truth)

    def test_complete_dump(self):
        self.assertEqual(check_dump(self.dump())['independent_bytes'], 1152)

    def test_corrupted_prefix_body_last_byte_or_guard_rejected(self):
        for offset in (0, 8, 39, 40, 135, 143):
            data = bytearray(expected(3)); data[offset] ^= 1
            text = self.dump().replace(expected(3).hex(), data.hex(), 1)
            with self.assertRaises(ValueError):
                check_dump(text)

    def test_missing_case_and_failed_selfcheck_rejected(self):
        for text in (self.dump().replace('RESTART8 7', 'MISSING 7'),
                     self.dump().replace(PASS_LINE, 'FAILED: masklogical_restart8')):
            with self.assertRaises(ValueError):
                check_dump(text)


if __name__ == '__main__':
    unittest.main()
