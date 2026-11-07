from pathlib import Path
import tempfile
import unittest

import collect_mmu_mxr_hit as c


class MXRCollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = c.LOG.read_text()
        cls.source = c.BENCH.read_text()

    def reject(self, text):
        with self.assertRaises(ValueError): c.check_log(text,self.source)

    def test_actual_quoted_inline_scope_records_bug_not_pass(self):
        value = c.check_log(self.log,self.source)
        self.assertEqual(value['state'],'MMU_MXR_HIT_PERMISSION_BUG_REPRODUCED')
        self.assertEqual(value['rtl_functional_status'],'FAIL')
        self.assertFalse(value['verified_coverage']); self.assertFalse(value['cold_ptw_covered'])
        self.assertEqual((value['cases'],value['checks'],value['mismatches']),(5,52,3))
        self.assertNotIn('\nScope:',self.log)

    def test_wrong_origin_even_when_fatal_and_finish_agree(self):
        for text in (self.log.replace(str(c.BENCH),'/other/mmu_mxr_hit_tb.sv'),
                     self.log.replace('mmu_mxr_hit_tb: at time','other_scope: at time')):
            self.reject(text)

    def test_wrong_line_and_finish_disagreement(self):
        for text in (self.log.replace(', 164:',', 163:'),
                     self.log.replace('line 164.','line 163.'),
                     self.log.replace(', 164:',', 163:').replace('line 164.','line 163.')):
            self.reject(text)

    def test_extra_fatal_any_file_or_midline(self):
        for extra in ('Fatal: /other.sv, 1: unrelated\n','noise Fatal: hidden\n',
                      next(line for line in self.log.splitlines() if line.startswith('Fatal:'))+'\n'):
            self.reject(self.log+extra)

    def test_reason_must_be_unique_and_immediately_follow_fatal(self):
        self.reject(self.log+c.REASON+'\n')
        self.reject(self.log.replace('\n'+c.REASON+'\n','\nnoise\n'+c.REASON+'\n'))
        self.reject(self.log.replace('\n'+c.REASON+'\n','\n'))

    def test_unexpected_errors_and_arbitrary_pass_text(self):
        for extra in ('Error: unrelated\n','Error-[OTHER] bad\n','UVM_ERROR : 1\n',
                      'ERROR unexpected\n','PASS\n','$stop\n','Scope: mmu_mxr_hit_tb\n'):
            self.reject(self.log+extra)

    def test_exactly_three_mismatches_no_noise_or_changed_expected(self):
        line = next(line for line in self.log.splitlines() if line.startswith('MMU_MXR_MISMATCH'))
        self.reject(self.log+line+'\n')
        self.reject(self.log.replace(line+'\n',''))
        self.reject(self.log.replace('field=EXCEPTION','field=EXCEPTION_NOISE'))
        self.reject(self.log.replace('expected=000000000000000d','expected=000000000000000c'))

    def test_every_observed_field_independently_rejected_on_change(self):
        lines = [line for line in self.log.splitlines() if line.startswith('MMU_MXR_HIT_OBS ')]
        for line in lines:
            words = line.split()
            for i,word in enumerate(words[1:],1):
                key,value = word.split('=')
                changed = int(value,16 if key in c.HEX else 10)+1
                replacement = f'{key}={changed:016x}' if key in c.HEX else f'{key}={changed}'
                mutated = words.copy(); mutated[i] = replacement
                with self.subTest(case=words[1],field=key):
                    self.reject(self.log.replace(line,' '.join(mutated),1))

    def test_missing_duplicate_reordered_and_unknown_observations(self):
        lines = [line for line in self.log.splitlines() if line.startswith('MMU_MXR_HIT_OBS ')]
        self.reject(self.log.replace(lines[0]+'\n',''))
        self.reject(self.log+lines[0]+'\n')
        self.reject(self.log.replace(lines[0],lines[1],1))
        self.reject(self.log.replace('latched_hit=1','latched_hit=x',1))

    def test_exact_summary_and_scope_required(self):
        for before,after in (('cases=5','cases=4'),('checks=52','checks=51'),('errors=3','errors=0'),
                             ('ptw_requests=0','ptw_requests=1'),('cold_ptw=0','cold_ptw=1')):
            self.reject(self.log.replace(before,after))
        self.reject(self.log+c.SUMMARY+'\n')

    def test_no_legacy_header_projection_or_synthetic_scope(self):
        self.reject(self.log.replace('Fatal: "','Fatal: ',1).replace('.sv", 164:', '.sv, 164:',1))
        self.reject(self.log.replace('\n'+c.REASON+'\n','\n'+c.REASON+'\nScope: mmu_mxr_hit_tb\n'))

    def test_source_binding_cannot_move_or_change_guard(self):
        for source in ('\n'+self.source,self.source.replace('if (errors) $fatal','if (0) $fatal')):
            with self.assertRaises(ValueError): c.check_log(self.log,source)

    def test_pin_mismatch_and_post_pin_drift_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'input'; path.write_bytes(b'original'); pins = {}
            c.bind(pins,path,c.digest(path)); c.verify(pins)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError): c.verify(pins)
            with self.assertRaises(ValueError): c.bind(pins,path)
            with self.assertRaises(ValueError): c.bind({},path,'0'*64)


if __name__=='__main__': unittest.main()
