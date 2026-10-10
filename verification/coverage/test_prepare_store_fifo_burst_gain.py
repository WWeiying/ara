"""Actual completed singleton and source binding; negatives never launch/admit."""
import copy
import json
import unittest
import prepare_store_fifo_burst_gain as p


class GainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = json.loads((p.q.p.BASE / 'combined-bits.json').read_bytes())
        directory = p.q.RUN / 'code.vdb/snps/coverage/db/testdata' / p.q.p.NAME
        cls.single = dict(design=cls.before['design'], tests=[str(p.q.RUN / 'code.vdb')],
                          input_hashes={str(directory / (m + '.verilog.data.xml')):
                                        p.life.digest(directory / (m + '.verilog.data.xml')) for m in p.bitmap.METRICS},
                          metrics={m: p.bitmap.read_metric(directory / (m + '.verilog.data.xml')) for m in p.bitmap.METRICS})
        cls.targets = p.q.p.target_binding()[0]
        cls.qual = p.life.read_bound(p.QUAL, p.QUAL_SEAL)

    def test_actual_complete6162_same_shape_OR(self):
        combined, delta = p.validate_population(self.before, self.single, 729)
        self.assertEqual(sum(len(v) for v in combined['metrics'].values()), 6162)
        self.assertEqual(combined['tests'][:-1], self.before['tests'])
        hits = p.target_hits(self.before, self.single, self.targets)
        self.assertEqual(len(hits), 8)
        self.assertTrue(all(t['before_hit'] is False for t in hits))
        self.assertEqual(p.candidate_status(delta, hits).startswith('STORE_FIFO_POSITIVE'),
                         any(t['fresh_target_gain'] for t in hits))

    def test_zero_or_incidental_gain_stays_hold(self):
        hits = [dict(fresh_target_gain=False)] * 8
        for delta in [dict(metrics=dict(line=0, cond=0, branch=0, fsm=0)),
                      dict(metrics=dict(line=10, cond=100, branch=10, fsm=0))]:
            self.assertIn('HOLD', p.candidate_status(delta, hits))

    def test_positive_exact_fifo_point_candidate(self):
        single = copy.deepcopy(self.single)
        t = self.targets[0]
        row = single['metrics'][t['metric']][t['scope']]
        row['bits'] = hex(int(row['bits'], 16) | (1 << (t['width'] - 1 - t['raw_index'])))
        _, delta = p.validate_population(self.before, single, 729)
        hits = p.target_hits(self.before, single, self.targets)
        self.assertTrue(hits[0]['fresh_target_gain'])
        self.assertIn('CANDIDATE_NOT_ADMITTED', p.candidate_status(delta, hits))

    def test_duplicate_population_or_sample_rejected(self):
        before = copy.deepcopy(self.before); before['tests'][1] = before['tests'][0]
        with self.assertRaises(ValueError): p.validate_population(before, self.single, 729)
        single = copy.deepcopy(self.single); single['tests'] = [self.before['tests'][0]]
        with self.assertRaises(ValueError): p.validate_population(self.before, single, 729)
        with self.assertRaises(ValueError): p.validate_population(self.before, self.single, 731)

    def test_missing_shape_checksum_width_or_overflow_rejected(self):
        scope = self.targets[0]['scope']
        for mode in ('missing', 'width', 'checksum', 'overflow'):
            single = copy.deepcopy(self.single)
            r = single['metrics']['branch'][scope]
            if mode == 'missing': del single['metrics']['branch'][scope]
            elif mode == 'width': r['width'] += 1
            elif mode == 'checksum': r['checksum'] = '1132753425'
            else: r['bits'] = hex(1 << r['width'])
            with self.assertRaises(ValueError): p.validate_population(self.before, single, 729)

    def test_branch_checksum_None_not_rewritten(self):
        combined, _ = p.validate_population(self.before, self.single, 729)
        scope = self.targets[0]['scope']
        self.assertIsNone(combined['metrics']['branch'][scope]['checksum'])
        self.assertEqual(self.targets[0]['shape_checksum'], '1132753425')

    def test_730_already_hit_is_witness_not_fresh(self):
        before = copy.deepcopy(self.before)
        before['tests'].append('/formal730/unique/code.vdb')
        t = self.targets[0]; row = before['metrics'][t['metric']][t['scope']]
        row['bits'] = hex(int(row['bits'], 16) | (1 << (t['width'] - 1 - t['raw_index'])))
        combined, _ = p.validate_population(before, self.single, 730)
        self.assertEqual(combined['tests'][:-1], before['tests'])
        hits = p.target_hits(before, self.single, self.targets)
        self.assertEqual(hits[0]['role'], 'ALREADY_HIT_WITNESS')
        self.assertFalse(hits[0]['fresh_target_gain'])

    def test_exact_eight_targets_only(self):
        with self.assertRaises(ValueError): p.target_hits(self.before, self.single, self.targets[:-1])
        with self.assertRaises(ValueError): p.target_hits(self.before, self.single, self.targets[:7] + self.targets[:1])

    def test_full_qualification_no_native_promotion(self):
        p.qualification(self.qual)
        for key in ('coverage_admitted', 'UVM_override_applied', 'FIFO_push_pop_measured', 'full_ISA_signoff'):
            record = copy.deepcopy(self.qual); record[key] = True
            with self.assertRaises(ValueError): p.qualification(record)

    def test_qualification_omitted_checks_rejected(self):
        for key, value in [('checks', 699), ('native_known_bytes', 127), ('OS_returncode', None), ('UVM_errors', 2)]:
            record = copy.deepcopy(self.qual); record[key] = value
            with self.assertRaises(ValueError): p.qualification(record)

    def test_real_sample_metadata_exact_command(self):
        prepared = p.life.read_bound(p.q.PREPARED, p.q.RUN_SEAL)
        directory = p.q.RUN / 'code.vdb/snps/coverage/db/testdata' / p.q.p.NAME
        metadata = p.sample_metadata(directory, prepared)
        self.assertTrue(metadata['raw_teststatus_not_used_as_PASS'])
        bad = copy.deepcopy(prepared); bad['command'][0] = '/other/simv'
        with self.assertRaises(ValueError): p.sample_metadata(directory, bad)

    def test_inherited_pin_conflict_rejected(self):
        with self.assertRaises(ValueError): p.life.merge_pins({'/x': 'a' * 64}, {'/x': 'b' * 64})

    def test_actual_formal730_full_prefix_and_shape(self):
        base = p.OUT / 'gap108-offline-admitted-730-parent-20261006-01'
        manifest = p.life.read_bound(base / 'admission-manifest.json',
            '8da19c3fba8b438851231dfc79c8006caeea2364f578c29f9afa3c6fbf91d3f5')
        before = p.life.read_bound(base / 'combined-bits.json', manifest['output_pins'][str(base / 'combined-bits.json')])
        self.assertEqual(before['tests'][:729], self.before['tests'])
        combined, _ = p.validate_population(before, self.single, 730)
        self.assertEqual(combined['tests'][:-1], before['tests'])
        self.assertEqual(len(p.target_hits(before, self.single, self.targets)), 8)


if __name__ == '__main__':
    unittest.main()
