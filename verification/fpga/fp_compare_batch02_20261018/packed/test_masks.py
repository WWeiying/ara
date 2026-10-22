#!/usr/bin/env python3
"""Exhaust all per-bit legal sets, including tail/masked-off alternatives."""
import itertools
import unittest


class PackedMasks(unittest.TestCase):
    def test_all_allowed_byte_sets(self):
        checks = 0
        for allowed in itertools.product(({0}, {1}, {0, 1}), repeat=8):
            zero = sum((1 not in a) << i for i, a in enumerate(allowed))
            one = sum((0 not in a) << i for i, a in enumerate(allowed))
            for actual in range(256):
                original = sum(((actual >> i) & 1) not in a for i, a in enumerate(allowed))
                packed = bin((actual & zero) | (~actual & one)).count('1')
                self.assertEqual(original, packed)
                checks += 1
        self.assertEqual(checks, 1679616)

    def test_guard_is_one_error_even_when_both_fail(self):
        for before, after in itertools.product((0, 0x5b, 255), repeat=2):
            self.assertEqual(int(before != 0x5b or after != 0x5b),
                             min(1, int(before != 0x5b) + int(after != 0x5b)))


if __name__ == '__main__':
    unittest.main()
