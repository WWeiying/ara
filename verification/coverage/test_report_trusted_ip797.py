import unittest
import report_trusted_ip797 as r


class ScopePolicy(unittest.TestCase):
    def setUp(self):
        self.root = r.policy.SCOPE + '.i_ara.i_fma'
        self.base = 'CHECKSUM: "3"\nINSTANCE: ' + self.root + '.leaf\nToggle v [3:0] "logic v[3:0]"\n'
        self.outside = 'CHECKSUM: "4"\nINSTANCE: ' + r.policy.SCOPE + '.i_dispatcher\nToggle ready "logic ready"\n'
        self.whole = 'CHECKSUM: "5"\nINSTANCE: ' + self.root + '\n'
        self.c = dict(trusted_roots={self.root: '5'},
                      retained_EL_seal=r.s.semantic_seal(r.normalized(self.base + self.outside, [self.root])))

    def test_native_whole_with_redundant_child(self):
        r.whole_gate(self.whole + self.base + self.outside, self.c)

    def test_native_whole_without_redundant_child(self):
        r.whole_gate(self.whole + self.outside, self.c)

    def test_missing_or_wrong_checksum_rejected(self):
        for text in (self.outside, self.whole.replace('"5"', '"6"') + self.outside):
            with self.assertRaises(ValueError): r.whole_gate(text, self.c)

    def test_non_target_changed_rejected(self):
        with self.assertRaises(ValueError): r.whole_gate(self.whole, self.c)

    def test_extra_parent_rejected(self):
        with self.assertRaises(ValueError):
            r.whole_gate(self.whole + self.outside + 'CHECKSUM: "9"\nINSTANCE: ' + r.policy.SCOPE + '\n', self.c)

    def test_namespace_prefix_not_owned(self):
        self.assertFalse(r.owned(self.root + '2', [self.root]))


if __name__ == '__main__': unittest.main()
