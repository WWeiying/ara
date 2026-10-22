import unittest
import audit_constant_suffix788 as p


class SuffixTests(unittest.TestCase):
    def fixture(self):
        return {'scope': dict(width=4, checksum='1', bits='0x5')}, [('family', {'scope': dict(width=4, checksum='1', positions=[0, 2])})]

    def test_target_zero_active_complement_retained(self):
        rows, groups = self.fixture()
        self.assertEqual(p.audit_rows(rows, groups)['family']['activated_directions'], 0)

    def test_newly_active_target_rejected(self):
        rows, groups = self.fixture(); rows['scope']['bits'] = '0xd'
        with self.assertRaisesRegex(ValueError, 'activated'): p.audit_rows(rows, groups)

    def test_wrong_checksum_rejected(self):
        rows, groups = self.fixture(); rows['scope']['checksum'] = '2'
        with self.assertRaisesRegex(ValueError, 'shape'): p.audit_rows(rows, groups)

    def test_missing_scope_rejected(self):
        _, groups = self.fixture()
        with self.assertRaisesRegex(ValueError, 'inventory'): p.audit_rows({}, groups)

    def test_duplicate_coordinate_rejected(self):
        rows, groups = self.fixture(); groups[0][1]['scope']['positions'] = [0, 0]
        with self.assertRaisesRegex(ValueError, 'shape'): p.audit_rows(rows, groups)

    def test_out_of_bounds_rejected(self):
        rows, groups = self.fixture(); groups[0][1]['scope']['positions'] = [4]
        with self.assertRaisesRegex(ValueError, 'bounded'): p.audit_rows(rows, groups)


if __name__ == '__main__': unittest.main()
