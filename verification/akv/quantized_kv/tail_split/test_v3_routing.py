from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verification.akv.quantized_kv.tail_split import coordinate_v3 as coordinator
from verification.akv.quantized_kv.tail_split import threeway_v2 as worker


class PrerequisiteRoutingTests(unittest.TestCase):
    def test_combine_redirect_changes_only_the_script(self):
        command = ['/usr/bin/python3', '-B', str(coordinator.HERE/'combine.py'),
                   '--runs', '/one', '/two', '/three', '/four', '--output', '/fresh']
        with tempfile.TemporaryDirectory() as temporary:
            owner = coordinator.Execution(Path(temporary))
            with patch.object(coordinator.BaseExecution, 'execute', return_value=0) as execute:
                owner.execute(command, Path(temporary)/'combine.log', 1800, 'COMBINING')
            actual = execute.call_args.args[0]
            self.assertEqual(actual[:2]+actual[3:], command[:2]+command[3:])
            self.assertEqual(actual[2], str(coordinator.HERE/'combine_v2.py'))
            self.assertEqual(command[2], str(coordinator.HERE/'combine.py'))

    def test_unknown_combine_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            owner = coordinator.Execution(Path(temporary))
            with patch.object(coordinator.BaseExecution, 'execute') as execute:
                with self.assertRaises(ValueError):
                    owner.execute(['/usr/bin/python3', '-B', 'wrong.py'], Path(temporary)/'log',
                                  1800, 'COMBINING')
                execute.assert_not_called()

    def test_other_command_policy_unchanged(self):
        command = ['/usr/bin/python3', '-B', 'preflight.py', '--preflight-only']
        with tempfile.TemporaryDirectory() as temporary:
            owner = coordinator.Execution(Path(temporary))
            with patch.object(coordinator.BaseExecution, 'execute', return_value=0) as execute:
                owner.execute(command, Path(temporary)/'log', 1800, 'DOWNSTREAM_PREFLIGHT')
            self.assertEqual(execute.call_args.args[0], command)

    def test_downstream_worker_preserves_all_arguments(self):
        target = dict(build='/build', prerequisite='/strided')
        old = coordinator.original_downstream_args(target, Path('/combined'), Path('/output'))
        new = coordinator.downstream_args(target, Path('/combined'), Path('/output'))
        self.assertEqual(new[:2]+new[3:], old[:2]+old[3:])
        self.assertEqual(new[2], str(coordinator.HERE/'threeway_v2.py'))
        self.assertEqual(new[-2:], ['--timeout', '10800'])

    def test_successor_admission_label_preserves_counts(self):
        original = dict(acceptance='TAIL_SPLIT_COMBINED_PASS', split_runs=4, commands=24,
                        state='ALL_FOUR_RAW_RECHECKED', tail=True)
        with patch.object(worker, 'original_checked_tails', return_value=dict(original)) as gate:
            result = worker.checked_tails('/combined', {'kind':'q4_0'}, {})
        gate.assert_called_once()
        self.assertEqual(result['acceptance'], worker.ACCEPTANCE)
        for field in ('split_runs', 'commands', 'state', 'tail'):
            self.assertEqual(result[field], original[field])
        with patch.object(worker, 'original_checked_tails', return_value=dict(acceptance='unknown')):
            with self.assertRaises(ValueError):
                worker.checked_tails('/combined', {}, {})


if __name__ == '__main__':
    unittest.main()
