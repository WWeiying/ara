import json
from pathlib import Path
import unittest

import lzc_selector_native_seven_policy_plan as subject


class SevenPlanTests(unittest.TestCase):
    def setUp(self):
        out = subject.OUT
        self.six = json.loads((out / 'branch-combo-six-policy-population-723-parent-20261006-02/config.json').read_bytes())
        proof = out / 'lzc-selector-native-cond60-four-state-review-723-20261006-01'
        review = json.loads((proof / 'review.json').read_bytes())
        self.review = review
        self.records = [r['native_record'] for r in review['candidates']]
        self.old = (Path(self.six['output']) / 'combined.el').read_bytes()
        self.extra = (proof / 'candidate60.el').read_bytes()

    def test_preserve_original_six_bytes_exact60_extra(self):
        self.assertEqual(subject.split_seven(self.old + self.extra, self.six, self.records),
                         (self.old, self.extra))

    def test_reject_false_vector_duplicate_and_extra_scope(self):
        for extra in (self.extra + self.extra,
                      self.extra.replace(b'(2 "1")', b'(2 "0")', 1),
                      self.extra.replace(self.records[0]['scope'].encode(), b'ara_tb.unapproved', 1)):
            with self.assertRaises(ValueError):
                subject.split_seven(self.old + extra, self.six, self.records)

    def test_reject_scope_ownership_overlap(self):
        changed = dict(self.six, scope_owners=dict(self.six['scope_owners'], **{self.records[0]['scope']: 'operand'}))
        with self.assertRaisesRegex(ValueError, 'ownership overlap'):
            subject.split_seven(self.old + self.extra, changed, self.records)

    def test_actual723_shape_binding_no_xml_gui_branch_guess(self):
        bitmap = json.loads((Path(self.six['admitted_base']) / 'combined-bits.json').read_bytes())
        design = subject.proof.Design(Path(self.six['inputs'][0]))
        self.assertEqual(len(subject.latest_binding(self.review, bitmap, design)), 60)
        changed = dict(self.review, exact_protection_rows=list(self.review['exact_protection_rows']))
        pos = next(i for i, r in enumerate(changed['exact_protection_rows']) if r['metric'] == 'cond')
        changed['exact_protection_rows'][pos] = dict(changed['exact_protection_rows'][pos], expression='DRIFT')
        with self.assertRaisesRegex(ValueError, 'ambiguous or absent'):
            subject.latest_binding(changed, bitmap, design)


if __name__ == '__main__':
    unittest.main()
