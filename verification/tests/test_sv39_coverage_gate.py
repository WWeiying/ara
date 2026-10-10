"""A PASS verdict alone must not open the coverage extension gate."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_gap34_20261001 as runner


def points(bits):
    return {'inputs': 'baseline', 'tests': 617, 'instances': {'mmu': {'branch': {
        'checksum': '42', 'total': 2, 'bits': bits, 'covered': bits.count('1'),
        'missing': [{'bit_index': i} for i, b in enumerate(bits) if b == '0']}}}}


class CoverageGateTest(unittest.TestCase):
    def run_gate(self, status, bits):
        calls, records = [], {}
        plan = {'simv': '/image/simv', 'design_vdb': '/image/simv.vdb'}
        item = {'status': status, 'passed_only': status == 'PASS', 'vdb': '/case/code.vdb'}
        baseline = points('10')

        def read(path):
            if path.name == 'plan.json':
                return plan
            if path == runner.BASELINE:
                return baseline
            return item

        def schedule(output, names, jobs):
            calls.append(list(names))
            (output / 'scheduler').mkdir()

        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            output = Path(temporary)
            stack.enter_context(patch.object(runner.full, 'read', side_effect=read))
            stack.enter_context(patch.object(runner.full, 'save', side_effect=lambda p, r: records.update({p.name: r})))
            stack.enter_context(patch.object(runner.full, 'original_schedule', side_effect=schedule))
            stack.enter_context(patch.object(runner.previous, 'admitted', return_value=[item]))
            stack.enter_context(patch.object(runner.point, 'audit', return_value=points(bits)))
            error = None
            try:
                runner.schedule(output, ['load', 'store', 'fetch'], 8)
            except ValueError as caught:
                error = str(caught)
        return calls, records, error

    def test_pass_without_gain_does_not_dispatch(self):
        calls, records, error = self.run_gate('PASS', '10')
        self.assertEqual(calls, [['load']])
        self.assertEqual(records['coverage-gate.json']['status'], 'NO_COVERAGE_GAIN')
        self.assertIn('no targeted gain', error)

    def test_fail_does_not_dispatch(self):
        calls, _, error = self.run_gate('FAIL', '11')
        self.assertEqual(calls, [['load']])
        self.assertIn('correctness gate failed', error)

    def test_gain_allows_remaining_cases(self):
        calls, records, error = self.run_gate('PASS', '01')
        self.assertIsNone(error)
        self.assertEqual(calls, [['load'], ['store', 'fetch']])
        self.assertEqual(records['coverage-gate.json']['new_points'], 1)
        self.assertEqual(records['coverage-gate.json']['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
