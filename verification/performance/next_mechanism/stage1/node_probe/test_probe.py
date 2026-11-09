import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent


class ProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.binary=Path(cls.temp.name)/'test_probe'
        subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                        '-I'+str(HERE),str(HERE/'test_probe.c'),str(HERE/'node_probe.c'),
                        '-Wl,--wrap=clock_gettime','-o',str(cls.binary)],check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_mode(self, mode):
        return json.loads(subprocess.check_output([str(self.binary),mode],text=True))

    def test_clock_and_metadata_modes_match_path(self):
        on,off=self.run_mode('on'),self.run_mode('off')
        self.assertTrue(on['valid'] and off['valid'])
        self.assertEqual(on['path_fingerprint_fnv1a64'],off['path_fingerprint_fnv1a64'])
        self.assertEqual(on['members'],3)
        self.assertEqual(on['units'],2)
        self.assertEqual(on['unit_ns'],2000)
        self.assertEqual(on['phase_ns'],5000)
        self.assertEqual(on['unattributed_ns'],3000)
        self.assertIsNone(off['phase_ns'])
        self.assertTrue(all(r['elapsed_ns'] is None for r in off['records']))
        self.assertIsNone(on['records'][1]['elapsed_ns'])
        self.assertEqual(on['records'][0]['name'],'quote"name')

    def test_failures_cannot_look_accepted(self):
        for mode,bit in [('overflow',4),('order',16),('execution',32),('clock',8),('workers',2)]:
            with self.subTest(mode=mode):
                report=self.run_mode(mode)
                self.assertFalse(report['valid'])
                self.assertTrue(report['errors'] & bit)
                self.assertIsNone(report['unit_ns'])

    def test_empty_graph_is_not_compute(self):
        r=self.run_mode('empty')
        self.assertEqual(r['unit_ns'],0)
        self.assertEqual(r['units'],0)
        self.assertEqual(r['members'],0)

    def test_exit_only_qbs_census_allowed(self):
        env=dict(os.environ,GGML_RISCV_QBS_TRACE='1')
        r=json.loads(subprocess.check_output([str(self.binary),'on'],text=True,env=env))
        self.assertTrue(r['valid'])


if __name__=='__main__':
    unittest.main()
