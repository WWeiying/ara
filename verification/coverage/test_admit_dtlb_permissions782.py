"""Focused offline admission gates; no simulation or admission writes."""
import copy
import unittest

import admit_dtlb_permissions782 as subject


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.before = dict(design={'shape': 'fixed'}, tests=['old'+str(i) for i in range(781)],
                           input_hashes={'/old-pin': 'a'*64}, metrics={})
        self.single = dict(design={'shape': 'fixed'}, tests=[str(subject.RUN/'code.vdb')],
                           input_hashes={'/new-pin': 'b'*64}, metrics={})
        for metric, count in subject.COUNTS.items():
            self.before['metrics'][metric] = {
                str(i): dict(width=3, checksum='fixed', bits='0x1') for i in range(count)}
            self.single['metrics'][metric] = {
                str(i): dict(width=3, checksum='fixed', bits='0x2') for i in range(count)}

    def test_exact_or_and_prefix(self):
        original = copy.deepcopy(self.before)
        result = subject.full_union(self.before, self.single)
        self.assertEqual(self.before, original)
        self.assertEqual(result['tests'][:-1], original['tests'])
        self.assertEqual(len(result['tests']), 782)
        self.assertTrue(all(row['bits']=='0x3' for rows in result['metrics'].values() for row in rows.values()))

    def test_duplicate_candidate_rejected(self):
        self.before['tests'][0] = self.single['tests'][0]
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)

    def test_duplicate_prefix_rejected(self):
        self.before['tests'][0] = self.before['tests'][1]
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)

    def test_design_rejected(self):
        self.single['design']['shape'] = 'changed'
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)

    def test_checksum_rejected(self):
        self.single['metrics']['fsm']['0']['checksum'] = 'changed'
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)

    def test_width_rejected(self):
        self.single['metrics']['fsm']['0']['width'] = 4
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)

    def test_extra_bit_rejected(self):
        self.single['metrics']['fsm']['0']['bits'] = '0x8'
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)

    def test_incomplete_metric_rejected(self):
        del self.single['metrics']['fsm']['0']
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)

    def test_conflicting_pin_rejected(self):
        self.before['input_hashes']['/same'] = 'a'*64
        self.single['input_hashes']['/same'] = 'b'*64
        with self.assertRaises(Exception): subject.full_union(self.before,self.single)


if __name__ == '__main__': unittest.main()
