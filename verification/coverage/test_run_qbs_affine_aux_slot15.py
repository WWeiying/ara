import unittest
from pathlib import Path
import run_qbs_affine_aux_slot15 as run


class Slot15(unittest.TestCase):
    def test_exact_scope(self):
        c = run.configuration('aux')
        self.assertTrue(c['ext_target'].endswith('entry_state_q[15]'))
        self.assertTrue(c['ext_guard'].endswith('entry_valid_q[15]'))
        self.assertEqual(len([v for v in c['ext_dump_objects'] if '.entry_state_q[' in v]),16)
        self.assertIn(run.SCOPE+'.entry_valid_q',c['ext_dump_objects'])

    def test_no_other_stage(self):
        for stage in ('scale','min_scale','aux15'):
            with self.assertRaises(ValueError): run.configuration(stage)

    def test_same_elf_image_no_force_dut(self):
        cmd = run.command('aux',Path('/tmp/slot15'))
        self.assertEqual(cmd[0],str(run.life.IMAGE))
        self.assertIn('+PRELOAD='+str(run.PRE/'qbs_affine_slot0_cancel.elf'),cmd)
        self.assertIn('+TESTCASE=qbs_affine_slot15_aux_external_reset',cmd)
        self.assertIn('+NO_FSDB',cmd)
        self.assertEqual(run.STAGES['aux'],(1,18*15+9))

    def test_marker_binding(self):
        c = run.configuration('aux')
        lines = ['EXT_RESET_READY %s 1'%c['ext_target'],'EXT_RESET_TARGET %s 1'%c['ext_target'],
                 'EXT_RESET_ASSERT',*[('EXT_RESET_LOW_EDGE %d'%i) for i in range(1,5)],
                 'EXT_RESET_RELEASE','EXT_RESET_DONE']
        run.backend().markers('\n'.join(lines),'aux')
        with self.assertRaises(ValueError):
            run.backend().markers('\n'.join(lines).replace('[15]','[0]'),'aux')


if __name__ == '__main__': unittest.main()
