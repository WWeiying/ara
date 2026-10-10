import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_csr_frozen_counter_simulation as r


class CSRRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = r.life.read_bound(r.PRE / 'preflight-manifest.json', r.PRE_SEAL)

    def test_real_preflight(self):
        pins = r.validate_preflight(self.pre)
        self.assertEqual(pins[str(r.ELF)], r.ELF_SHA)

    def reject_preflight(self, change):
        pre = copy.deepcopy(self.pre)
        change(pre)
        with self.assertRaises(ValueError):
            r.validate_preflight(pre)

    def test_wrong_baseline(self):
        self.reject_preflight(lambda p: p.__setitem__('baseline_tests', 737))

    def test_bool_int_rejected(self):
        self.reject_preflight(lambda p: p.__setitem__('VCS_authorized', 0))

    def test_missing_trace_pin(self):
        self.reject_preflight(lambda p: p['output_pins'].pop(str(r.PRE / 'spike.trace')))

    def test_wrong_elf(self):
        self.reject_preflight(lambda p: p['output_pins'].__setitem__(str(r.ELF), '0' * 64))

    def test_command_fixed(self):
        out = r.life.OUT / 'csr-counter-unit-command'
        command = r.command(out)
        self.assertEqual(command[0], str(r.life.IMAGE))
        self.assertIn('+NO_FSDB', command)
        self.assertIn('+PRELOAD=' + str(r.ELF), command)
        self.assertIn('+COMMIT_TRACE=' + str(out / 'commit_trace.csv'), command)
        self.assertIn('+VECTOR_TRACE=' + str(out / 'vector_trace.csv'), command)
        self.assertNotIn('+FSDB', command)

    def test_private_lifecycle_no_mutation_or_launch(self):
        before = (r.frozen.PRE, r.frozen.BUDGET, r.frozen.command, r.frozen.preflight)
        with patch.object(r.frozen.subprocess, 'Popen', side_effect=AssertionError('No launch')):
            ns = r.lifecycle_namespace()
        self.assertEqual((r.frozen.PRE, r.frozen.BUDGET, r.frozen.command, r.frozen.preflight), before)
        self.assertEqual(ns['BUDGET'], 120)
        self.assertEqual(ns['PRE'], r.PRE)
        self.assertEqual(ns['ELF_SEAL'], r.ELF_SHA)
        self.assertEqual(ns['preflight'].NAME, r.NAME)
        self.assertIs(ns['command'], r.command)
        self.assertIsNot(ns['run'], r.frozen.run)

    def test_real_reference_counts(self):
        commits = r.oracle.shared.parse_spike_commits(r.PRE / 'spike.trace')
        counts = r.reference_counts(commits, 0x80000000, self.pre['symbols']['tohost'])
        self.assertEqual([counts[k] for k in ('matched_instructions', 'matched_scalar_writes',
                          'matched_scalar_memory_accesses')], [782, 434, 203])

    def test_incomplete_terminal_rejected(self):
        c = SimpleNamespace(pc=0x80000000, instruction=0x13, gpr_writes={}, vector_writes={}, memory_accesses=())
        with self.assertRaises(ValueError):
            r.reference_counts([c], c.pc, 0x1000)

    def test_compressed_rejected(self):
        c = SimpleNamespace(pc=0x80000000, instruction=1, gpr_writes={}, vector_writes={},
                            memory_accesses=((0x1000, 1),))
        with self.assertRaises(ValueError):
            r.reference_counts([c], c.pc, 0x1000)

    def test_authorization_required(self):
        with patch.object(r, 'prepare', side_effect=AssertionError('Must not prepare or launch')):
            with self.assertRaises(ValueError):
                r.main(['run', '--output', str(r.life.OUT / 'not-launched'), '--prepared-seal', '0' * 64])

    def test_wrong_prepared_command(self):
        with patch.object(r, 'prepare', return_value={'command': ['exact']}):
            with self.assertRaises(ValueError):
                r.verify_prepared(Path('/unused'), {'command': ['different']})

    def test_actual_manifest_no_launch(self):
        out = r.life.OUT / 'csr-counter-unit-manifest-not-created'
        with patch.object(r.frozen.subprocess, 'Popen', side_effect=AssertionError('No launch')):
            record = r.manifest(out)
        self.assertFalse(out.exists())
        self.assertEqual(record['timeout_s'], 120)
        self.assertEqual(record['old_image_files_checked'], 66)
        self.assertEqual(len(record['targets']), 7)
        self.assertEqual(record['qualification_contract']['skipped_scalar_values'], 0)
        self.assertFalse(record['qualification_contract']['partial_or_prefix_allowed'])
        self.assertFalse(record['coverage_admitted'])


if __name__ == '__main__':
    unittest.main()
