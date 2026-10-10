import unittest
from pathlib import Path
from unittest.mock import patch
import run_fclass_divsqrt783 as r

CALLS = []


def fake_worker(out, manifest):
    CALLS.append((BUDGET, PRE, ELF_SEAL, IMAGE_SEAL, preflight.NAME, command(out), manifest))


class Runner(unittest.TestCase):
    def test_command_no_rebuild_or_wave(self):
        out = r.life.OUT / 'test-fclass-command'
        cmd = r.command(out)
        self.assertEqual(cmd[0], str(r.life.IMAGE))
        self.assertIn('+PRELOAD=' + str(r.ELF), cmd)
        self.assertIn('+NO_FSDB', cmd)
        self.assertIn('line+cond+fsm+tgl+branch', cmd)
        self.assertEqual(cmd.count('-cm_dir'), 1)
        self.assertIn(str(out / 'code.vdb'), cmd)

    def test_actual_frozen_preflight(self):
        pre = r.preflight()
        self.assertEqual(pre['counts']['cases'], 75)
        self.assertEqual(pre['counts']['runtime']['entry_to_tohost_instructions'], 165928)
        self.assertEqual(r.BUDGET, 900)

    def test_wrong_counts_rejected(self):
        pre = r.life.read_bound(r.PRE, r.PRE_SHA)
        pre['counts']['checks'] = 2250
        with patch.object(r.life, 'read_bound', return_value=pre), patch.object(r.life, 'check'):
            with self.assertRaises(ValueError): r.preflight()

    def test_actual_baseline(self):
        _, bits, lines = r.baseline()
        self.assertEqual(len(lines), 784)
        self.assertEqual(len(bits['tests']), 783)
        self.assertEqual(sum(len(v) for v in bits['metrics'].values()), 6162)

    def test_existing_output_rejected_without_explicit_terminal(self):
        with self.assertRaises(ValueError): r.prepare(r.PRE.parent)

    def test_outside_output_rejected(self):
        with self.assertRaises(ValueError): r.prepare(Path('/tmp/fclass-test'))

    def test_worker_budget_and_authorization_wiring(self):
        CALLS.clear()
        with patch.object(r.template.inherited.worker, 'run', fake_worker):
            r.invoke_run(r.life.OUT / 'test-worker', {'case': r.NAME})
        budget, pre, elf, image, name, cmd, manifest = CALLS[0]
        self.assertEqual((budget, pre, elf, image, name), (900, r.ELF.parent, r.ELF_SHA, r.IMAGE_SHA, r.NAME))
        self.assertIn('+NO_FSDB', cmd)
        self.assertEqual(manifest['authorization_source'], 'PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL')


if __name__ == '__main__': unittest.main()
