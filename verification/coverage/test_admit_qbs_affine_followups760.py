import copy
import unittest
from unittest.mock import patch
import admit_qbs_affine_followups760 as a


class Followups(unittest.TestCase):
    def test_real_qualified_scope(self):
        for stage, _, _, sha, directory, _, _ in a.CASES:
            a.contract(a.life.read_bound(a.life.OUT/directory/'qualification.json', sha), stage)

    def test_scope_claims_rejected(self):
        stage, _, _, sha, directory, _, _ = a.CASES[0]
        qual = a.life.read_bound(a.life.OUT/directory/'qualification.json', sha)
        for key, bad in [('baseline',758), ('stage','aux'), ('checks',True),
                         ('full_scalar_ISA_verified',True), ('uvm_check_report_pass',True),
                         ('reset_stage_and_slot_reuse_wave_verified',False)]:
            changed = copy.deepcopy(qual); changed[key] = bad
            with self.assertRaises(ValueError): a.contract(changed, stage)

    def fixture(self):
        metrics = {m: {'s':dict(width=1,checksum='1',bits='0x0')} for m in a.q.bitmap.METRICS}
        return (dict(tests=['old'],metrics=metrics,design={},input_hashes={}),
                dict(tests=['new'],metrics=copy.deepcopy(metrics),design={},input_hashes={}))

    def test_duplicate_rejected(self):
        before, single = self.fixture(); single['tests']=['old']
        with self.assertRaises(ValueError): a.merge(before,single,1,'old')

    def test_wrong_population_rejected(self):
        before, single = self.fixture()
        with self.assertRaises(ValueError): a.merge(before,single,2,'new')

    def test_missing_shape_rejected(self):
        before, single = self.fixture(); single['metrics']['fsm']={}
        with self.assertRaises(ValueError): a.merge(before,single,1,'new')

    def test_checksum_rejected(self):
        before, single = self.fixture(); single['metrics']['fsm']['s']['checksum']='2'
        with self.assertRaises(ValueError): a.merge(before,single,1,'new')

    def test_actual_serial_or(self):
        book = a.life.read_bound(a.BASE/'admission-manifest.json', a.BASE_SHA)
        before = a.life.read_bound(a.BASE/'combined-bits.json', book['output_pins'][str(a.BASE/'combined-bits.json')])
        for offset, (stage, _, _, sha, directory, run, _) in enumerate(a.CASES):
            qual = a.life.read_bound(a.life.OUT/directory/'qualification.json', sha)
            path = a.life.OUT/directory/'single-bits.json'
            single = a.life.read_bound(path, qual['output_pins'][str(path)])
            previous = before
            before, delta = a.merge(before, single, 758+offset, a.life.OUT/run/'code.vdb')
            self.assertEqual(before['tests'][:-1], previous['tests'])
            self.assertGreater(sum(delta['metrics'].values()), 0)

    def test_actual_zero_gain_rejected(self):
        book = a.life.read_bound(a.BASE/'admission-manifest.json', a.BASE_SHA)
        before = a.life.read_bound(a.BASE/'combined-bits.json', book['output_pins'][str(a.BASE/'combined-bits.json')])
        single = copy.deepcopy(before)
        single['tests'] = ['new-zero-gain']
        with self.assertRaisesRegex(ValueError, 'Zero gain'):
            a.merge(before, single, 758, 'new-zero-gain')


if __name__ == '__main__': unittest.main()
