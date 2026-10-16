import importlib.util
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'coverage/audit_probe_semantics_20261015.py'
spec = importlib.util.spec_from_file_location('probe_semantics_audit', HELPER)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ProbeSemanticsAuditTest(unittest.TestCase):
    def test_akv_inventory_does_not_require_uncaptured_tb_clock(self):
        directory = audit.ROOT / 'verification/out/full-regression-failure-review-20261015-01/probe-semantics/final02/e0789'
        if not (directory / 'probe.vcd').is_file():
            self.skipTest('Current AKV VCD fixture not installed')
        case = object.__new__(audit.CaseAudit)
        case.out, case.inputs = directory, {}
        result = case.probe_inventory()
        self.assertNotIn('ara_tb.clk', result['declarations'])
        self.assertTrue(any(name.endswith('.clk_i') for name in result['declarations']))

    def csr_fixture(self, index):
        case_path = audit.RUNS / f'e{index:04d}'
        if not (case_path / 'plan.json').is_file():
            self.skipTest('Current replay fixture not installed')
        plan = json.loads((case_path / 'plan.json').read_text())
        case = object.__new__(audit.CaseAudit)
        case.index, case.case = index, case_path
        case.old = json.loads(Path(plan['command_source']).read_text())
        name = 'run_csr_satp_sepc786' if index == 786 else 'run_csr_cause_wlrl788'
        runner = importlib.import_module(name)
        pre = json.loads((runner.PRE / 'preflight-manifest.json').read_text())
        shared = importlib.import_module('collect_csr_satp_sepc786')
        rows = shared.primitive.parse_rows(case_path / 'work/commit_trace.csv')
        return case, rows, runner.reference(pre), pre, runner.oracle

    def test_actual_csr_values_and_mutated_csr_rejection(self):
        for index in (786, 788):
            with self.subTest(index=index):
                case, rows, reference, pre, oracle = self.csr_fixture(index)
                self.assertTrue(case.csr_architectural(rows, reference, pre, oracle)['CSR_values_and_restoration_verified'])
                bad = [dict(row) for row in rows]
                addresses = (0x180, 0x141) if index == 786 else (0x342, 0x142)
                target = next(row for row in bad if row['insn'] & 127 == 0x73 and row['insn'] >> 20 in addresses and row['rd'])
                target['rd_wdata'] ^= 1
                with self.assertRaisesRegex(ValueError, 'Actual CSR/GPR'):
                    case.csr_architectural(bad, reference, pre, oracle)

    def test_actual_csr_store_mask_corruption_rejects(self):
        case, rows, reference, pre, oracle = self.csr_fixture(786)
        bad = [dict(row) for row in rows]
        next(row for row in bad if row['mem_wmask'])['mem_wmask'] ^= 1
        with self.assertRaisesRegex(ValueError, 'Exact store source/data/mask'):
            case.csr_architectural(bad, reference, pre, oracle)

    def test_input_pin_mismatch_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input'
            path.write_text('actual')
            case = object.__new__(audit.CaseAudit)
            case.inputs = {}
            with self.assertRaisesRegex(ValueError, 'Input pin mismatch'):
                case.bind(path, '0' * 64)

    def test_input_drift_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input'
            path.write_text('first')
            case = object.__new__(audit.CaseAudit)
            case.inputs = {}
            case.bind(path)
            path.write_text('second')
            with self.assertRaisesRegex(ValueError, 'Input drift'):
                case.bind(path)

    def test_clean_execution_alone_cannot_pass_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            case = object.__new__(audit.CaseAudit)
            case.index, case.out, case.inputs = 782, Path(directory), {}
            case.components = {'execution': {'status': 'PASS'}}
            result = case.finish()
            self.assertEqual(result['status'], 'CHECKER_REQUIRED')
            self.assertIn('native', result['missing_components'])
            self.assertEqual(result['functional_status'], 'CHECKER_REQUIRED')

    def test_qbs_functional_and_micro_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            case = object.__new__(audit.CaseAudit)
            case.index, case.out, case.inputs = 782, Path(directory), {}
            case.components = {name: {'status': 'PASS'} for name in ('execution', 'native', 'dispatch')}
            result = case.finish()
            self.assertEqual(result['functional_status'], 'PASS')
            self.assertEqual(result['micro_witness'], 'CHECKER_REQUIRED')

    def test_akv_required_fault_drain_wave_cannot_be_waived(self):
        with tempfile.TemporaryDirectory() as directory:
            case = object.__new__(audit.CaseAudit)
            case.index, case.out, case.inputs = 789, Path(directory), {}
            case.components = {name: {'status': 'PASS'} for name in ('execution', 'native', 'dispatch', 'perf', 'source_context')}
            result = case.finish()
            self.assertEqual(result['functional_status'], 'CHECKER_REQUIRED')
            self.assertIn('wave', result['missing_components'])

    def guarded_child(self, operation):
        with tempfile.TemporaryDirectory() as directory:
            code = (
                'import importlib.util,pathlib,subprocess; '
                f's=importlib.util.spec_from_file_location("a",{str(HELPER)!r}); '
                'a=importlib.util.module_from_spec(s); s.loader.exec_module(a); '
                f'a.install_guard(pathlib.Path({directory!r})); ' + operation
            )
            return subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)

    def test_guard_blocks_old_directory_write(self):
        result = self.guarded_child('pathlib.Path("/tmp/audit-must-not-write").write_text("bad")')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('outside output', result.stderr)

    def test_guard_blocks_nonconverter_process(self):
        result = self.guarded_child('subprocess.run(["/usr/bin/true"])')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Only VPD conversion permitted', result.stderr)


if __name__ == '__main__':
    unittest.main()
