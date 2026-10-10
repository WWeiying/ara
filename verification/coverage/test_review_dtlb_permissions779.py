"""Focused independent Sv39 permission gold negatives; no simulator."""
import unittest

from review_dtlb_permissions779 import cases, permission


class PermissionGold(unittest.TestCase):
    def test_exact_cases(self):
        rows = cases()
        self.assertEqual(len(rows), 9)
        self.assertEqual([r['mcause'] for r in rows], [0, 13, 0, 13, 15, 13, 0, 0, 15])

    def test_sum(self):
        self.assertEqual(permission(0x79, 'S', 'load', mxr=True), 13)
        self.assertEqual(permission(0x79, 'S', 'load', sum_enabled=True, mxr=True), 0)

    def test_mxr(self):
        self.assertEqual(permission(0x79, 'U', 'load', mxr=True), 0)
        self.assertEqual(permission(0x79, 'U', 'load', mxr=False), 13)

    def test_user_cannot_use_supervisor_page(self):
        self.assertEqual(permission(0xc7, 'U', 'load', sum_enabled=True, mxr=True), 13)
        self.assertEqual(permission(0xc7, 'U', 'store', sum_enabled=True), 15)

    def test_dirty_and_write_independent(self):
        self.assertEqual(permission(0x47, 'S', 'load'), 0)
        self.assertEqual(permission(0x47, 'S', 'store'), 15)
        self.assertEqual(permission(0xc3, 'S', 'store'), 15)
        self.assertEqual(permission(0xc7, 'S', 'store'), 0)

    def test_invalid_and_accessed(self):
        for flags in (0xc6, 0x87, 0xc5):
            for op, cause in (('load', 13), ('store', 15)):
                self.assertEqual(permission(flags, 'S', op, mxr=True, sum_enabled=True), cause)

    def test_global_has_no_permission_power(self):
        for flags in range(256):
            for priv in ('S', 'U'):
                for op in ('load', 'store'):
                    self.assertEqual(permission(flags, priv, op), permission(flags ^ 32, priv, op))


if __name__ == '__main__':
    unittest.main()
