import unittest
from pathlib import Path
import subprocess
import run_csr_satp_sepc786 as p


class RunnerTests(unittest.TestCase):
    def test_command_budget_and_probe(self):
        out = p.life.OUT / 'csr-run-host-fixture'
        cmd = p.command(out)
        self.assertEqual(cmd[0], str(p.life.IMAGE))
        self.assertIn('+PRELOAD=' + str(p.ELF), cmd)
        self.assertIn('+NO_FSDB', cmd)
        self.assertEqual(cmd[-3:], ['-ucli', '-do', str(p.PROBE)])
        self.assertEqual(p.BUDGET, 180)

    def test_source_contract_actual(self):
        proof, pins = p.source_contract()
        p.life.check(pins)
        self.assertEqual(proof['ops'], dict(CSR_WRITE=33, CSR_READ=34, CSR_SET=35, CSR_CLEAR=36))
        self.assertEqual(proof['tid_width'], 3)

    def test_real_private_run_globals(self):
        ns = p.lifecycle_namespace(p.life.OUT / 'host-unlaunched-fixture', {'command': [], 'service': p.SERVICE})
        self.assertIs(ns['run'].__globals__, ns)
        self.assertEqual(ns['BUDGET'], 180)
        self.assertIs(ns['command'], p.command)
        self.assertEqual(ns['subprocess'].STDOUT, subprocess.STDOUT)
        self.assertIs(ns['subprocess'].TimeoutExpired, subprocess.TimeoutExpired)
        self.assertIsNot(ns['subprocess'].Popen, subprocess.Popen)
        self.assertEqual(p.template.frozen.BUDGET, 600)

    def test_reference_real_counts(self):
        pre = p.life.read_bound(p.PRE / 'preflight-manifest.json', p.PRE_SEAL)
        ref = p.reference(pre)
        counts = p.template.reference_counts(ref, 0x80000000, pre['symbols']['tohost'])
        self.assertEqual([counts[k] for k in ('matched_instructions', 'matched_scalar_writes',
                         'matched_scalar_memory_accesses')], [673, 388, 168])
        self.assertEqual(p.oracle.validate(ref, pre['symbols']), pre['validation'])

    def test_parent_authorization_gate(self):
        import sys
        from unittest.mock import patch
        argv = ['runner', 'run', '--output', str(p.life.OUT / 'never-run'), '--prepared-seal', 'wrong']
        with patch.object(sys, 'argv', argv), self.assertRaisesRegex(ValueError, 'authorization'):
            p.main()

    def test_invalid_service_rejected_before_inputs(self):
        with self.assertRaisesRegex(ValueError, 'owning'):
            p.manifest(p.life.OUT / 'never-run', '../other.service')

    def test_probe_is_readonly_exact(self):
        text = p.PROBE.read_text()
        self.assertNotRegex(text, r'(?m)^\s*(?:force|deposit|stop)\b')
        self.assertIn('${buffer}.fu_data_i.trans_id', text)
        self.assertIn('${csr}.commit_instr_i.trans_id', text)
        self.assertIn('${csr}.commit_ack_i', text)


if __name__ == '__main__': unittest.main()
