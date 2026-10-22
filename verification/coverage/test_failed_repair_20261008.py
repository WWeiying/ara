import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_failed_repair_20261008 as repair


class RepairAcceptanceTests(unittest.TestCase):
    def test_axpy_performance_regression_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'run.vcs.log').write_text(
                'Core Test *** SUCCESS ***\n[PERF] total_cycles : 2811')
            with patch.object(repair.operands, 'check_contract_log', return_value=[]), \
                 patch.object(repair.base, 'sha256', return_value='same-elf'), \
                 patch.object(repair.base, 'read', return_value={'status': 'PASS', 'cycles': 2810}), \
                 patch.object(repair, 'check_real_uvm_log', return_value={'status': 'PASS'}):
                with self.assertRaisesRegex(RuntimeError, 'performance regression'):
                    repair.audit(directory, 'axpy')

    def test_original_failures_are_gate_one(self):
        self.assertEqual(repair.FOCUSED, ['vgap76_red16', 'mask_restart', 'qbs_canonical',
            'vgap101_illegal_segment_store', 'vmemory_emul_r2_boundary_reject', 'vgap112_sv39_fof'])
        names = repair.FOCUSED + repair.NEIGHBOURS
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertTrue((repair.source(name) / 'input.elf').is_file(), name)

    def test_scalar_rejects_unordered_reduction_even_if_vector_checker_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'run.vcs.log').write_text('Core Test *** SUCCESS ***')
            (directory / 'input.elf').write_bytes(bytes(24) + (0x80000000).to_bytes(8, 'little'))
            commits = [SimpleNamespace(memory_accesses=((0x1000, 1), (0x2000, 1820), (0x2004, 0)))]
            with patch.object(repair.operands, 'check_contract_log', return_value=[]), \
                 patch.object(repair.operands, '_elf_symbol', side_effect=[0x1000, 0x2000]), \
                 patch.object(repair.operands, 'parse_spike_commits', return_value=commits), \
                 patch.object(repair.operands, 'compare_commit_prefix', return_value={'status': 'MISMATCH'}), \
                 patch.object(repair.operands, 'compare_vector_commits', return_value={'status': 'PASS'}):
                with self.assertRaisesRegex(RuntimeError, 'strict scalar/vector'):
                    repair.audit(directory, 'vgap76_red16')

    def test_process_success_without_selfcheck_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'run.vcs.log').write_text('simulation exited 0')
            with patch.object(repair.operands, 'check_contract_log', return_value=[]):
                with self.assertRaisesRegex(RuntimeError, 'self-check'):
                    repair.audit(directory, 'vgap76_red16')

    def test_assertion_failure_is_rejected_despite_success_banner(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'run.vcs.log').write_text('Core Test *** SUCCESS ***')
            with patch.object(repair.operands, 'check_contract_log', return_value=['failure']):
                with self.assertRaisesRegex(RuntimeError, 'contract'):
                    repair.audit(directory, 'vgap76_red16')

    def test_carry_requires_all_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'run.vcs.log').write_text('Core Test *** SUCCESS ***\ngap35 checks=458 failures=0')
            with patch.object(repair.operands, 'check_contract_log', return_value=[]):
                with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                    repair.audit(directory, 'vgap35_carry_ta')


if __name__ == '__main__':
    unittest.main()
