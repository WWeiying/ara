import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('power_v3_tested', HERE/'precheck_power_v3.py')
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)


class PowerSuccessorTests(unittest.TestCase):
    def numeric(self):
        return dict(state='POWER_ELIGIBLE', strict_numerical_state='FAIL',
            relative_power_eligible=True, execution_path_checked=True,
            exhaustive_target_comparisons=True, strict_failure_preserved=True,
            hash_only_validation=False, power_acceptance=False,
            original_numerical_result_reclassified=False)

    def test_preserves_non_pass_state_and_failure(self):
        case = dict(checker_success_state='POWER_ELIGIBLE')
        numeric = self.numeric()
        v3.check_eligibility(case, numeric, dict(state='FAIL'))
        self.assertEqual(numeric['state'], 'POWER_ELIGIBLE')
        for key in ('relative_power_eligible', 'execution_path_checked',
                    'exhaustive_target_comparisons', 'strict_failure_preserved'):
            bad = dict(numeric, **{key: False})
            with self.subTest(key=key), self.assertRaises(ValueError):
                v3.check_eligibility(case, bad, dict(state='FAIL'))
        for key in ('hash_only_validation', 'power_acceptance', 'original_numerical_result_reclassified'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                v3.check_eligibility(case, dict(numeric, **{key: True}), dict(state='FAIL'))
        with self.assertRaises(ValueError):
            v3.check_eligibility(case, dict(numeric, state='PASS'), dict(state='FAIL'))
        with self.assertRaises(ValueError):
            v3.check_eligibility(case, numeric, dict(state='PASS'))

    def test_protocol_gates_unchanged(self):
        case = dict(elf_sha256='elf')
        proof = dict(status='PASS', issues=[], contract_counts=dict(exceptions=0, protocol_errors=0,
            outstanding=0), elf_sha256='elf', simv_sha256='sim', log_sha256='log', vector_trace_sha256='vec')
        v3.check_protocol(proof, case, 'sim', 'log', 'vec')
        for key in ('exceptions', 'protocol_errors', 'outstanding'):
            bad = copy.deepcopy(proof)
            bad['contract_counts'][key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                v3.check_protocol(bad, case, 'sim', 'log', 'vec')
        for key in ('elf_sha256', 'simv_sha256', 'log_sha256', 'vector_trace_sha256', 'status', 'issues'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                v3.check_protocol(dict(proof, **{key: 'bad'}), case, 'sim', 'log', 'vec')

    def test_real_strict_command_no_synthesized_log(self):
        case = dict(checker=['python3', '-B', '/checker.py', 'eligibility', '--build', '/build',
                    '--log', '{log}', '--commit', '{run}/commit.csv', '--output', '{result}'])
        argv = v3.strict_command(case, dict(log='/raw.log', run='/run', result='/power.json', strict='/strict.json'))
        self.assertIn('check', argv)
        self.assertNotIn('--commit', argv)
        self.assertEqual(argv[argv.index('--log')+1], '/raw.log')
        self.assertEqual(argv[argv.index('--output')+1], '/strict.json')

    def test_counts_existing_simulators_and_ignores_zombies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for pid, name, status in ((1, 'simv', 'S'), (2, 'simv', 'R'), (3, 'simv', 'Z'), (4, 'python3', 'S')):
                directory = root/str(pid)
                directory.mkdir()
                (directory/'comm').write_text(name+'\n')
                (directory/'stat').write_text('%d (%s) %s 0 0\n' % (pid, name, status))
            self.assertEqual(v3.live_simulators(root), [1, 2])

    def test_frozen_worker_only(self):
        with self.assertRaisesRegex(ValueError, 'Frozen'):
            v3.execute(Path('/tmp/not-a-frozen-worker'))


if __name__ == '__main__':
    unittest.main()
