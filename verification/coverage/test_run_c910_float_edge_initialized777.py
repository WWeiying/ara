from pathlib import Path
from unittest.mock import patch
import unittest
import run_c910_float_edge_initialized777 as r


class InitializedRunner(unittest.TestCase):
    def test_real_preflight_and_prepare_no_EDA(self):
        pre = r.preflight()
        self.assertEqual(pre['counts']['initialization']['bytes'],3072)
        out = r.life.OUT / 'c910-initialized-unittest-not-created'
        with patch.object(r,'invoke_run',side_effect=AssertionError('No EDA')):
            manifest = r.prepare(out)
        self.assertEqual(manifest['timeout_s'],600)
        self.assertEqual(manifest['scalar_reference_instructions'],36997)
        self.assertEqual(manifest['elf_sha256'],r.ELF_SHA)
        self.assertEqual(manifest['systemd_policy']['RuntimeMaxSec'],660)
        self.assertFalse(out.exists())

    def test_command_exact_same_image_new_ELF(self):
        out = r.life.OUT/'c910-initialized-unittest-not-created'
        command = r.command(out)
        self.assertEqual(command[0],str(r.life.IMAGE))
        self.assertIn('+PRELOAD='+str(r.ELF),command)
        self.assertIn('+ntb_random_seed=1',command)
        self.assertIn('line+cond+fsm+tgl+branch',command)

    def test_uninitialized_preflight_rejected(self):
        from copy import deepcopy
        pre = deepcopy(r.preflight()); pre['counts']['initialization']['bytes'] = 32
        with patch.object(r.life,'read_bound',return_value=pre):
            with self.assertRaises(ValueError): r.preflight()


if __name__=='__main__': unittest.main()
