import copy
import unittest
import review_trusted_execution797_system_v2 as r


class SystemBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = r.collect()

    def test_actual_bound_sources_and_scope(self):
        r.validate(self.packet)
        self.assertEqual(len(self.packet['outside_scope_REMOVED_NOT_APPROVED']), 48)

    def test_scope_not_namespace_prefix(self):
        self.assertFalse(r.inside(r.SCOPE + '2.i_lzc'))
        self.assertFalse(r.inside('ara_tb.dut.i_ara_soc.i_uart.i_lzc'))

    def test_exact_root_and_descendant(self):
        self.assertTrue(r.inside(r.SCOPE))
        self.assertTrue(r.inside(r.SCOPE + '.i_lzc'))

    def test_outside_injection_rejected(self):
        packet = copy.deepcopy(self.packet)
        packet['candidates'].append(packet['outside_scope_REMOVED_NOT_APPROVED'][0])
        with self.assertRaises(ValueError):
            r.validate(packet)

    def test_known_bug_cannot_be_recommended(self):
        packet = copy.deepcopy(self.packet)
        next(t for t in packet['candidates'] if t['module'] == 'simd_alu')['decision'] = 'RECOMMEND'
        with self.assertRaises(ValueError):
            r.validate(packet)

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            r.restrict([self.packet['candidates'][0]] * 2)

    def test_roots_cannot_expand(self):
        packet = copy.deepcopy(self.packet)
        packet['minimal_recommended_roots'].append('ara_tb.dut.i_ara_soc.i_uart')
        with self.assertRaises(ValueError):
            r.validate(packet)

    def test_parent_root_replaces_nested_leaf(self):
        selected, removed, roots = r.restrict([
            dict(scope=r.SCOPE + '.i_fma', decision='RECOMMEND'),
            dict(scope=r.SCOPE + '.i_fma.i_lzc', decision='RECOMMEND')])
        self.assertEqual(roots, [r.SCOPE + '.i_fma'])


if __name__ == '__main__':
    unittest.main()
