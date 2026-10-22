import unittest
from unittest.mock import patch
import run_c910_float_edge777 as run


class BoundedRun(unittest.TestCase):
    def test_command_exact_elf(self):
        command = run.command(run.life.OUT / 'c910-run-test')
        self.assertEqual(command.count('+PRELOAD=' + str(run.ELF)), 1)
        self.assertIn('+NO_FSDB', command)
        self.assertEqual(command[command.index('-cm') + 1], 'line+cond+fsm+tgl+branch')
    def test_actual_preflight(self): self.assertEqual(run.preflight()['counts']['checks'], 1440)
    def test_actual_prepare_no_eda_no_output(self):
        out = run.life.OUT / 'c910-float-edge-host-prepare-test-no-directory'
        self.assertFalse(out.exists())
        result = run.prepare(out)
        self.assertEqual((result['baseline'], result['timeout_s'], result['old_image_files_checked']), (777, 600, 66))
        self.assertEqual(result['systemd_policy']['RuntimeMaxSec'], 660)
        self.assertFalse(out.exists())
    def test_existing_directory_not_fresh(self):
        with self.assertRaises(ValueError): run.prepare(run.PRE.parent)
    def test_outside_output_rejected(self):
        with self.assertRaises(ValueError): run.prepare(run.life.ROOT / 'not-a-run')
    def test_preflight_drift_rejected(self):
        with patch.object(run.life, 'check', side_effect=ValueError('drift')):
            with self.assertRaises(ValueError): run.preflight()
    def test_wrong_instruction_count(self):
        pre = run.life.read_bound(run.PRE, run.PRE_SHA)
        pre['counts']['runtime']['entry_to_tohost_instructions'] = 36956
        with patch.object(run.life, 'read_bound', return_value=pre), patch.object(run.life, 'check'):
            with self.assertRaises(ValueError): run.preflight()
    def test_no_gain_claim(self): self.assertEqual(len(run.SIGNALS), 7)


if __name__ == '__main__': unittest.main()
