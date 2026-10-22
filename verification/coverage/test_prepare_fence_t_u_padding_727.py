import inspect
from pathlib import Path
import unittest
import prepare_fence_t_u_padding_727 as s


class RebindTests(unittest.TestCase):
    def test_frozen_original_and_only_population_rebind(self):
        self.assertEqual(s.old.sha(Path(s.old.__file__)),s.SOURCE_SHA)
        function=s.adapted()
        self.assertEqual(function.__globals__['BASE'],s.BASE)
        self.assertEqual(function.__globals__['BASE_SHA'],s.BASE_SHA)
        self.assertEqual(function.__globals__['BUILD'],s.old.BUILD)
        self.assertIn(727,function.__code__.co_consts)
        self.assertNotIn(726,function.__code__.co_consts)

    def test_build_no_eda_or_shared_make(self):
        text=s.BUILD.read_text()
        self.assertIn("r['relative_admission_population']==727",text)
        self.assertIn('timeout --kill-after=5s 30s',text)
        self.assertNotIn('make -C',text)
        self.assertNotIn('simv',text)
        self.assertNotIn('spike ',text)
        self.assertIn('PENDING_ELF_AUDIT_NO_SPIKE_NO_VCS',text)

    def test_actual727_primary_and_witness_bits(self):
        import json
        manifest_path=s.BASE/'admission-manifest.json'
        self.assertEqual(s.old.sha(manifest_path),s.BASE_SHA)
        manifest=json.loads(manifest_path.read_bytes());path=s.BASE/'combined-bits.json'
        self.assertEqual(s.old.sha(path),manifest['output_pins'][str(path)])
        bitmap=json.loads(path.read_bytes());self.assertEqual(len(set(bitmap['tests'])),727)
        for instance,metric,indices in [('controller_i','branch',[1,33,36]),
            ('controller_i','cond',[29,31,33,40,41,42,43,44,45,46,50]),
            ('csr_regfile_i','branch',[520]),('csr_regfile_i','line',[780])]:
            record=bitmap['metrics'][metric][s.old.PREFIX+instance]
            for index in indices:
                self.assertFalse(int(record['bits'],16)&(1<<(record['width']-1-index)))
        self.assertIn('corroborating_witness',s.adapted().__code__.co_consts)


if __name__=='__main__':unittest.main()
