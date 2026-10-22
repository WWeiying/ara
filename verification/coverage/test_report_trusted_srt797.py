import copy
import unittest
from unittest.mock import patch

import report_trusted_srt797 as r


class NativeBoundary(unittest.TestCase):
    def setUp(self):
        self.old = r.review_tool.SYSTEM + '.old_ip'
        self.new = r.review_tool.SYSTEM + '.core'
        self.outside = r.review_tool.SYSTEM + '.control'
        self.inherited = 'CHECKSUM: "2"\nINSTANCE: ' + self.old + '\nANNOTATION: "historical"\n'
        self.control = 'CHECKSUM: "3"\nINSTANCE: ' + self.outside + '\nToggle ready "logic ready"\n'
        self.point = 'CHECKSUM: "5"\nINSTANCE: ' + self.new + '.table\nToggle data "logic data"\n'
        self.whole = 'CHECKSUM: "4"\nINSTANCE: ' + self.new + '\nANNOTATION: "' + r.native.ANNOTATION + '"\n'
        self.c = dict(trusted_roots={self.old: '2', self.new: '4'}, new_trusted_roots={self.new: '4'},
                      retained_EL_seal=r.s.semantic_seal(r.prior.normalized(self.inherited + self.control + self.point, [self.new])))

    def test_whole_inherited_annotation_preserved(self):
        r.whole_gate(self.inherited + self.control + self.whole, self.c)

    def test_redundant_inside_points_allowed(self):
        r.whole_gate(self.inherited + self.control + self.whole + self.point, self.c)

    def test_same_annotation_reordered_allowed(self):
        reordered = 'CHECKSUM: "4"\nANNOTATION: "' + r.native.ANNOTATION + '"\nINSTANCE: ' + self.new + '\n'
        r.whole_gate(self.inherited + self.control + reordered, self.c)

    def test_wrong_or_missing_new_annotation(self):
        for whole in (self.whole.replace(r.native.ANNOTATION, 'wrong'),
                      self.whole.split('ANNOTATION:')[0]):
            with self.assertRaises(ValueError):
                r.whole_gate(self.inherited + self.control + whole, self.c)

    def test_wrong_checksum(self):
        with self.assertRaises(ValueError):
            r.whole_gate(self.inherited + self.control + self.whole.replace('"4"', '"9"'), self.c)

    def test_duplicate_new_whole(self):
        with self.assertRaises(ValueError):
            r.whole_gate(self.inherited + self.control + self.whole * 2, self.c)

    def test_extra_descendant(self):
        extra = self.whole.replace(self.new, self.new + '.extra')
        with self.assertRaises(ValueError):
            r.whole_gate(self.inherited + self.control + self.whole + extra, self.c)

    def test_extra_ancestor(self):
        extra = self.whole.replace(self.new, r.review_tool.SYSTEM)
        with self.assertRaises(ValueError):
            r.whole_gate(self.inherited + self.control + self.whole + extra, self.c)

    def test_lost_inherited_or_control(self):
        for text in (self.control + self.whole, self.inherited + self.whole):
            with self.assertRaises(ValueError):
                r.whole_gate(text, self.c)

    def test_protected_point_changed(self):
        with self.assertRaises(ValueError):
            r.whole_gate(self.inherited + self.control.replace('ready', 'valid') + self.whole, self.c)

    def test_namespace_not_owned(self):
        self.assertFalse(r.prior.owned(self.new + '2', [self.new]))

    def test_same_raw_and_protected_reports(self):
        baseline = {stage: {self.outside: {'Toggle': '10%'}} for stage in r.s.STAGES}
        r.protected_gate(copy.deepcopy(baseline), baseline, [self.new])
        changed = copy.deepcopy(baseline)
        changed['applied'][self.outside]['Toggle'] = '20%'
        changed['reloaded'] = copy.deepcopy(changed['applied'])
        with self.assertRaises(ValueError):
            r.protected_gate(changed, baseline, [self.new])

    def test_raw_change_rejected(self):
        baseline = {stage: {self.outside: {'Toggle': '10%'}} for stage in r.s.STAGES}
        changed = copy.deepcopy(baseline)
        for stage in ('raw', 'reset', 'final'):
            changed[stage][self.outside]['Toggle'] = '20%'
        with self.assertRaises(ValueError):
            r.protected_gate(changed, baseline, [self.new])

    def test_no_second_attempt(self):
        with patch.object(r.Path, 'exists', return_value=True):
            with self.assertRaises(ValueError):
                r.run(r.s.OUT / 'fake', 'seal', 'seal')


if __name__ == '__main__':
    unittest.main()
