"""No simulator launch: exact contracts and frozen lifecycle rebinding/restoration."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import run_store_fifo_burst_simulation as r


def preflight():
    return dict(status=r.p.STATUS, case=r.p.NAME, baseline_tests=729, baseline_manifest_sha256=r.p.BASE_SEAL,
                checks=2360, vcs_started=False, rtl_changed=False, coverage_admitted=False,
                measured_raw_increment=None, duplicate729_ELF=False, input_elf_sha256='e' * 64,
                symbols=dict(tohost=0x80001000), pins={str(r.PRE / 'input.elf'): 'e' * 64},
                targets=[dict(hit729=False, native_GUI_binding=False) for _ in range(8)],
                validation=dict(status=r.p.STATUS, checks=2360, bursts=7, target_stores=56, lengths=list(r.p.LENGTHS),
                                destination_words=2016, source_words=36, source_dump_words=252, CSR_words=56,
                                exceptions=0, coverage_admitted=False, native_scheduling_measured=False))


class RunnerTests(unittest.TestCase):
    def test_valid_exact_contract(self):
        r.validate(preflight())

    def test_wrong_scope_or_population_rejected(self):
        for key, value in [('case', 'vpure_war_div_indexed_load'), ('baseline_tests', 728), ('coverage_admitted', True)]:
            pre = preflight(); pre[key] = value
            with self.assertRaises(ValueError): r.validate(pre)

    def test_reduced_oracle_rejected(self):
        for key, value in [('checks', 699), ('target_stores', 55), ('exceptions', 1)]:
            pre = preflight(); pre['validation'][key] = value
            with self.assertRaises(ValueError): r.validate(pre)

    def test_target_hit_rejected(self):
        pre = preflight(); pre['targets'][0]['hit729'] = True
        with self.assertRaises(ValueError): r.validate(pre)

    def test_exact_image_trace_command(self):
        out = r.life.OUT / 'store-burst-test-never-run'
        command = r.command(out)
        self.assertEqual(command[0], str(r.life.IMAGE))
        self.assertIn('+PRELOAD=' + str(r.PRE / 'input.elf'), command)
        self.assertIn('+NO_FSDB', command)
        self.assertIn('line+cond+fsm+tgl+branch', command)
        self.assertEqual(r.BUDGET, 600)

    def test_scoped_foreground_bindings_restored(self):
        out = r.life.OUT / 'store-burst-test-never-run'
        manifest = dict(command=r.command(out), timeout_s=600, baseline_tests=729,
                        coverage_admitted=False, elf_sha256='e' * 64)
        original = {n: getattr(r.frozen, n) for n in ('PRE', 'ELF_SEAL', 'preflight', 'command')}
        def capture(actual_out, actual_manifest):
            self.assertEqual(actual_out, out)
            self.assertIs(actual_manifest, manifest)
            self.assertEqual(r.frozen.PRE, r.PRE)
            self.assertIs(r.frozen.preflight, r.p)
            self.assertEqual(r.frozen.ELF_SEAL, 'e' * 64)
        with patch.object(r.frozen, 'run', side_effect=capture) as mocked:
            r.invoke_run(out, manifest)
            mocked.assert_called_once()
        self.assertEqual({n: getattr(r.frozen, n) for n in original}, original)

    def test_error_restores_bindings(self):
        out = r.life.OUT / 'store-burst-test-never-run'
        manifest = dict(command=r.command(out), timeout_s=600, baseline_tests=729,
                        coverage_admitted=False, elf_sha256='e' * 64)
        original = r.frozen.PRE
        with patch.object(r.frozen, 'run', side_effect=RuntimeError('mock failure')):
            with self.assertRaises(RuntimeError): r.invoke_run(out, manifest)
        self.assertEqual(r.frozen.PRE, original)

    def test_no_extended_budget(self):
        out = r.life.OUT / 'store-burst-test-never-run'
        manifest = dict(command=r.command(out), timeout_s=601, baseline_tests=729,
                        coverage_admitted=False, elf_sha256='e' * 64)
        with patch.object(r.frozen, 'run') as mocked:
            with self.assertRaises(ValueError): r.invoke_run(out, manifest)
            mocked.assert_not_called()


if __name__ == '__main__':
    unittest.main()
