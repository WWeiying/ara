"""Case/budget/foreground lifetime guards, without simulator execution."""
from pathlib import Path
from unittest.mock import patch
import unittest

import run_sv39_masked_unit_fault_simulation as r


class RunnerTests(unittest.TestCase):
    def test_command(self):
        output=r.life.OUT/'masked-test'
        cmd=r.command(output)
        self.assertEqual(cmd[0],str(r.life.IMAGE))
        self.assertIn('+NO_FSDB',cmd)
        self.assertIn('+PRELOAD='+str(r.PRE/'input.elf'),cmd)
        self.assertEqual(cmd[-1],r.NAME)
        self.assertEqual(cmd[cmd.index('-cm_dir')+1],str(output/'code.vdb'))

    def test_budget(self):
        self.assertEqual(r.BUDGET,180)
        self.assertEqual(r.BASE_SEAL,'4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397')

    def test_exact_rejects_bool(self):
        with self.assertRaises(ValueError): r.exact({'count':True},{'count':1},'count')

    def test_old_lifecycle_private(self):
        original=r.frozen.run.__globals__['BUDGET']
        manifest={'x':1,'elf_sha256':'e'}
        with patch.object(r,'prepare',return_value=manifest):
            # Execute a minimal substitute body to inspect the same wiring.
            def body(out,manifest): return BUDGET,PRE,command(out)
            with patch.object(r.frozen,'run',body):
                value=r.invoke_run(r.life.OUT/'test',manifest)
                self.assertEqual(value,(180,r.PRE,r.command(r.life.OUT/'test')))
        self.assertEqual(r.frozen.run.__globals__['BUDGET'],original)

    def test_output_rejected(self):
        for path in (Path('/tmp/bad'),r.PRE):
            with self.assertRaises(ValueError): r.prepare(path)

    def test_unauthorized_cli(self):
        with patch('sys.argv',['run','run','--output',str(r.life.OUT/'never-start'), '--prepared-seal','0'*64]):
            with patch.object(r,'prepare',side_effect=AssertionError('must not prepare/launch')):
                with self.assertRaises(ValueError):r.main()


if __name__=='__main__': unittest.main()
