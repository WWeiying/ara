import unittest
from pathlib import Path
import run_qbs_affine_min_slot15 as run


class MinSlot(unittest.TestCase):
    def test_correct_min_not_aux(self):
        c = run.configuration('min_scale')
        self.assertEqual(c['ext_value'],3)
        self.assertTrue(c['ext_guard'].endswith('[15]'))
        self.assertEqual(run.STAGES,{'min_scale':(3,284)})
        with self.assertRaises(ValueError): run.configuration('aux')

    def test_same_image_elf(self):
        cmd = run.command('min_scale',Path('/tmp/min15'))
        self.assertEqual(cmd[0],str(run.life.IMAGE))
        self.assertIn('+PRELOAD='+str(run.PRE/'qbs_affine_slot0_cancel.elf'),cmd)
        self.assertIn('+TESTCASE=qbs_affine_slot15_min_scale_external_reset',cmd)

    def test_prepare_adapter_exact_offsets(self):
        fn = run.prepared_function(dict(run.template.prepare.__globals__))
        self.assertIn(284,fn.__code__.co_consts)
        self.assertNotIn(279,fn.__code__.co_consts)
        self.assertNotIn('aux',fn.__code__.co_consts)

    def test_complete_snapshot_dump(self):
        dumps = run.configuration('min_scale')['ext_dump_objects']
        self.assertIn(run.SCOPE+'.entry_valid_q',dumps)
        self.assertEqual(len([v for v in dumps if '.entry_state_q[' in v]),16)


if __name__ == '__main__': unittest.main()
