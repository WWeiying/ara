import copy
import unittest

import admit_queue_mask_740 as a


class UnionTests(unittest.TestCase):
    def setUp(self):
        metrics = {m: {} for m in a.bitmap.METRICS}
        metrics['cond'] = {'ara_tb.dut.i_ara_soc.i_system.p%d' % i:
            dict(width=1, checksum='123', bits='0') for i in range(6162)}
        self.before = dict(design={'shape': 'a'}, tests=['/sealed/test%d' % i for i in range(739)],
            input_hashes={'/sealed/before': 'a'*64}, metrics=metrics)
        self.single = copy.deepcopy(self.before)
        self.single['tests'] = ['/sealed/single']
        self.single['input_hashes'] = {'/sealed/single': 'b'*64}
        for i in range(4): self.single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system.p%d' % i]['bits'] = '1'

    def test_full_or(self):
        combined, delta = a.union(self.before, self.single)
        self.assertEqual(combined['tests'], self.before['tests'] + self.single['tests'])
        self.assertEqual(delta['metrics'], dict(line=0, cond=4, branch=0, fsm=0))

    def rejected(self):
        with self.assertRaises((ValueError, RuntimeError)): a.union(self.before, self.single)

    def test_duplicate(self):
        self.single['tests'] = [self.before['tests'][0]]; self.rejected()

    def test_wrong_baseline_count(self):
        self.before['tests'].pop(); self.rejected()

    def test_empty_raw_provenance(self):
        self.single['input_hashes'] = {}; self.rejected()

    def test_conflicting_raw_provenance(self):
        self.single['input_hashes'] = {'/sealed/before': 'b'*64}; self.rejected()

    def test_shape(self):
        self.single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system.p0']['checksum'] = '456'; self.rejected()

    def test_design(self):
        self.single['design'] = {'shape': 'b'}; self.rejected()

    def test_missing_instance(self):
        self.single['metrics']['cond'].popitem(); self.rejected()

    def test_out_of_range(self):
        self.single['metrics']['cond']['ara_tb.dut.i_ara_soc.i_system.p0']['bits'] = '2'; self.rejected()

    def test_zero_gain(self):
        self.single['metrics'] = copy.deepcopy(self.before['metrics']); self.rejected()


if __name__ == '__main__': unittest.main()
