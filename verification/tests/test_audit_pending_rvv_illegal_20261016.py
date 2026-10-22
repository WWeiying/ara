"""Agent-owned negative tests; mutate private fixtures only, never run evidence."""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).resolve().parents[1] / 'coverage/audit_pending_rvv_illegal_20261016.py'
spec = importlib.util.spec_from_file_location('pending_rvv_illegal_audit', HELPER)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditPolicyTest(unittest.TestCase):
    def test_exact_nine_case_ownership(self):
        self.assertEqual(audit.CASES, (715, 717, 718, 719, 721, 722, 725, 736, 737))
        self.assertEqual(set(audit.MODULES), set(audit.CASES))

    def test_real_numeric_predicate_failure_is_FAIL(self):
        self.assertEqual(audit.classify_error(ValueError('VRF/target/guard/recovery mismatch')), 'FAIL')

    def test_source_guard_and_dependency_are_not_DUT_failure(self):
        for error in (ValueError('Frozen observed oracle changed'), ModuleNotFoundError('elftools'),
                      audit.ContextRequired('Reference pin missing')):
            self.assertEqual(audit.classify_error(error), 'CHECKER_REQUIRED')

    def test_clean_execution_alone_cannot_PASS(self):
        with tempfile.TemporaryDirectory() as directory:
            item = object.__new__(audit.Audit)
            item.index, item.out, item.work, item.case = 715, Path(directory), Path('/current/work'), Path('/current')
            item.input_pins = {}
            item.components = {'execution': {'status': 'PASS'}}
            result = item.finish()
            self.assertEqual(result['status'], 'CHECKER_REQUIRED')
            self.assertTrue(result['missing_predicates'])

    def guarded_child(self, action):
        with tempfile.TemporaryDirectory() as directory:
            code = ('import importlib.util,pathlib,subprocess; '
                f's=importlib.util.spec_from_file_location("audit",{str(HELPER)!r}); '
                'a=importlib.util.module_from_spec(s); s.loader.exec_module(a); '
                f'a.install_guard(pathlib.Path({directory!r})); ' + action)
            return subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)

    def test_process_launch_is_blocked(self):
        result = self.guarded_child('subprocess.run(["/usr/bin/true"])')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('prohibits process launch', result.stderr)

    def test_old_output_write_is_blocked(self):
        result = self.guarded_child('pathlib.Path("/tmp/rvv-audit-must-not-write").write_text("bad")')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('write outside output', result.stderr)


class ActualIllegalOracleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = audit.RUNS / 'e0715'
        if not (cls.case / 'plan.json').is_file():
            raise unittest.SkipTest('Current replay fixture not installed')
        import collect_gap101a_strict_v2 as original
        import collect_opivx_vsbc_strict as common
        cls.q, cls.common = original, common
        plan = json.loads((cls.case / 'plan.json').read_text())
        old = json.loads(Path(plan['command_source']).read_text())
        cls.symbols = old['preflight']['symbols']
        cls.reference = Path(old['preflight']['input_spike_trace'])
        cls.rows = common.read_csv((cls.case / 'work/commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
        cls.vectors = common.read_csv((cls.case / 'work/vector_trace.csv').read_bytes(), common.VECTOR_FIELDS)

    def test_real_lifecycle_and_missing_response_rejection(self):
        self.assertEqual(self.q.lifecycle(self.rows, self.vectors)['rejected_backend_uops'], 0)
        bad = list(self.rows)
        bad.pop(next(i for i, row in enumerate(bad) if row['event'] == 'cvx_resp'))
        with self.assertRaises(ValueError):
            self.q.lifecycle(bad, self.vectors)

    def test_real_guard_trap_oracle_and_corrupted_cause_rejection(self):
        self.assertEqual(self.q.observed(self.rows, self.symbols)['checks'], 539)
        bad = [dict(row) for row in self.rows]
        candidates = [row for row in bad if row['event'] == 'retire' and int(row['mem_wmask'], 16)
                      and int(row['mem_addr'], 16) == self.symbols['g101a_ledger']]
        self.assertTrue(candidates)
        candidates[-1]['mem_wdata'] = '%016x' % (int(candidates[-1]['mem_wdata'], 16) ^ 1)
        with self.assertRaises(ValueError):
            self.q.observed(bad, self.symbols)

    def test_actual_VRF_byte_corruption_rejects(self):
        from ara_verify.vector_commit import compare_vector_commits
        control = self.q.lifecycle(self.rows, self.vectors)
        bad = [dict(row) for row in self.vectors]
        row = next(row for row in bad if row['event'] == 'write' and int(row['be'], 16))
        enable = int(row['be'], 16)
        byte = next(i for i in range(8) if enable >> i & 1)
        row['wdata'] = '%016x' % (int(row['wdata'], 16) ^ (1 << (8 * byte)))
        with tempfile.TemporaryDirectory() as directory:
            commit = Path(directory) / 'commit.csv'
            vector = Path(directory) / 'vector.csv'
            shutil.copyfile(self.case / 'work/commit_trace.csv', commit)
            with vector.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=self.common.VECTOR_FIELDS)
                writer.writeheader()
                writer.writerows(bad)
            result = compare_vector_commits(self.reference, commit, vector, 0x80000000)
            with self.assertRaises(ValueError):
                self.q.vector_exact(result, control['exception_arch_seq'])

    def test_extra_tracer_exception_rejects(self):
        text = (self.case / 'work/trace_hart_0.log').read_text()
        self.q.tracer_exact(text, self.rows, self.symbols)
        with self.assertRaises(ValueError):
            self.q.tracer_exact(text + '\nException @ 80000000, PC: 80000000, Cause: Illegal Instruction\n', self.rows, self.symbols)


class CurrentMaintenanceOracleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case = audit.RUNS / 'e0725'
        comparison = audit.DEFAULT_OUT / 'e0725/vector-comparison.json'
        if not comparison.is_file():
            raise unittest.SkipTest('Actual current VNCLIPU comparison fixture not installed')
        import qualify_vnclipu_parent_terminal as original
        from ara_verify.spike_trace import parse_spike_commits
        plan = json.loads((case / 'plan.json').read_text())
        old = json.loads(Path(plan['command_source']).read_text())
        prepath = Path(old['preflight'])
        pre = json.loads(prepath.read_text())
        cls.result = json.loads(comparison.read_text())
        cls.rows = original.common.read_csv((case / 'work/commit_trace.csv').read_bytes(), original.common.COMMIT_FIELDS)
        cls.vectors = original.common.read_csv((case / 'work/vector_trace.csv').read_bytes(), original.common.VECTOR_FIELDS)
        cls.reference = list(parse_spike_commits(prepath.parent / 'spike.trace'))
        cls.control = original.lifecycle(cls.rows, cls.vectors, pre['symbols'])

    def check(self, vectors=None, result=None):
        return audit.vnclipu_maintenance(self.result if result is None else result, self.rows,
            self.vectors if vectors is None else vectors, self.reference, self.control)

    def source(self, vectors):
        return next(row for row in vectors if row['event'] == 'write' and row['arch_seq'] == '124' and row['vd'] == '8')

    def test_actual_retimed_maintenance_all_bytes_known(self):
        before = json.dumps(self.result, sort_keys=True)
        proof = self.check()
        self.assertEqual(proof['known_source_maintenance_bytes'], 128)
        self.assertEqual(proof['genuinely_unknown_bytes'], 0)
        self.assertNotEqual(proof['actual_start'], 101168)
        self.assertEqual(json.dumps(self.result, sort_keys=True), before)

    def test_corrupted_known_source_byte_rejects(self):
        vectors = [dict(row) for row in self.vectors]
        row = self.source(vectors)
        row['wdata'] = '%016x' % (int(row['wdata'], 16) ^ 1)
        with self.assertRaisesRegex(ValueError, 'byte mismatch'):
            self.check(vectors=vectors)

    def test_unknown_source_byte_rejects(self):
        vectors = [dict(row) for row in self.vectors]
        self.source(vectors)['wdata'] = 'xxxxxxxxxxxxxxxx'
        with self.assertRaisesRegex(ValueError, 'Unknown enabled'):
            self.check(vectors=vectors)

    def test_unowned_phase_write_rejects(self):
        vectors = [dict(row) for row in self.vectors]
        self.source(vectors)['cycle'] = '0'
        with self.assertRaisesRegex(ValueError, 'exactly one actual phase'):
            self.check(vectors=vectors)

    def test_extra_unknown_elsewhere_not_reclassified(self):
        result = json.loads(json.dumps(self.result))
        result['instructions'][0]['skipped_unknown_bytes'] = 1
        with self.assertRaisesRegex(ValueError, 'Only exact proved maintenance'):
            self.check(result=result)


if __name__ == '__main__':
    unittest.main()
