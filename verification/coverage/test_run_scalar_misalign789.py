import unittest
from pathlib import Path
from unittest.mock import patch
import run_scalar_misalign789 as r


class Runner(unittest.TestCase):
    def test_exact_command_frozen_elf_and_readonly_probe(self):
        out=r.life.OUT/'scalar-misalign789-test-never-run'
        argv=r.command(out)
        self.assertIn(str(r.PROBE), argv)
        self.assertTrue(any(str(r.ELF) in s for s in argv))
        self.assertIn('-ucli',argv)
        self.assertEqual(r.BUDGET,120)
        self.assertEqual(r.life.digest(r.ELF),r.ELF_SHA)
    def test_actual_reference(self):
        pre=r.life.read_bound(r.PRE/'preflight-manifest.json',r.PRE_SEAL)
        ref=r.reference(pre)
        self.assertEqual(len(ref),866)
        self.assertEqual(r.oracle.validate(ref,pre['symbols'],r.oracle.traps(
            (r.PRE/'spike.trace').read_text(),pre['symbols'])),pre['validation'])
    def test_prepare_rejects_existing_output_before_manifest(self):
        with self.assertRaises(ValueError):r.verify_prepared(r.PRE,{})
    def test_terminal_not_prepare_gate(self):
        with patch.object(r,'manifest',return_value={'service':r.SERVICE}):
            self.assertEqual(r.verify_prepared(r.PRE,{'service':r.SERVICE},terminal=True),{'service':r.SERVICE})
    def test_private_subprocess_keeps_stdout_and_run_namespace(self):
        out=r.life.OUT/'scalar-misalign789-test-never-run'
        ns=r.lifecycle_namespace(out,dict(command=r.command(out),service=r.SERVICE))
        self.assertIs(ns['run'].__globals__,ns)
        self.assertTrue(hasattr(ns['subprocess'],'STDOUT'))
        self.assertEqual(ns['BUDGET'],120)
        self.assertEqual(ns['command'](out),r.command(out))
    def test_foreign_service_rejected(self):
        with self.assertRaises(ValueError):r.manifest(r.life.OUT/'scalar-misalign-test','other.scope')


if __name__ == '__main__':unittest.main()
