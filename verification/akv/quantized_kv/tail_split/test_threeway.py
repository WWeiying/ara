"""Successor gate routing tests using synthetic receipts, never actual VCS acceptance."""
import copy
from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split import threeway as gate
from verification.akv.quantized_kv.tail_split import test_split as fixtures

PREFIX = 'verification.akv.quantized_kv.tail_split.threeway.'


class ThreewayGateTests(unittest.TestCase):
    def setup_tails(self, stack, mutation=None):
        dirs = [gate.HERE, gate.PARENT, gate.ROOT, gate.ROOT / 'verification']
        records = fixtures.SplitTests().records()
        image = {'simv': 'test-image'}
        triples = [(r, {'accepted_image_pins': dict(image)}, {'synthetic': 'b' * 64}) for r in records]
        inherited = {str(p / 'result.json'): 'a' * 64 for p in dirs}
        inherited['synthetic'] = 'b' * 64
        if mutation:
            mutation(triples, inherited)
        combined = stack.enter_context(patch(PREFIX + 'checked_combined', return_value={'runs': list(map(str, dirs))}))
        raw = stack.enter_context(patch(PREFIX + 'checked_run', side_effect=triples))
        stack.enter_context(patch.object(gate.s, 'read_json', return_value=inherited))
        stack.enter_context(patch.object(gate.s, 'digest', return_value='a' * 64))
        stack.enter_context(patch.object(gate.s, 'hashes', return_value={}))
        stack.enter_context(patch.object(gate.s, 'verify_pins'))
        return {'kind': 'q4_0', 'accepted_image_pins': image}, combined, raw

    def test_all_four_raw_replayed(self):
        with ExitStack() as stack:
            target, combined, raw = self.setup_tails(stack)
            result = gate.checked_tails(gate.HERE, target, {})
            combined.assert_called_once()
            self.assertEqual(raw.call_count, 4)
            self.assertEqual(result['commands'], 24)
            self.assertEqual(result['state'], 'ALL_FOUR_RAW_RECHECKED')

    def test_incomplete_combined_never_reaches_raw_or_launch(self):
        with ExitStack() as stack:
            target, combined, raw = self.setup_tails(stack)
            combined.side_effect = ValueError('Not all four terminal PASS')
            with self.assertRaises(ValueError):
                gate.checked_tails(gate.HERE, target, {})
            raw.assert_not_called()

    def test_image_pin_matrix_failure(self):
        def wrong_image(triples, _pins):
            triples[3][1]['accepted_image_pins'] = {'simv': 'wrong'}

        def missing_pin(_triples, pins):
            del pins['synthetic']

        def failed_member(triples, _pins):
            triples[0][0]['state'] = 'TIMEOUT'

        def duplicate_member(triples, _pins):
            triples[3] = copy.deepcopy(triples[0])

        for mutate in (wrong_image, missing_pin, failed_member, duplicate_member):
            with ExitStack() as stack:
                target, _combined, _raw = self.setup_tails(stack, mutate)
                with self.assertRaises(ValueError):
                    gate.checked_tails(gate.HERE, target, {})

    def test_strided_gate_retained(self):
        target = dict(kind='q4_0', accepted_image_pins={'simv': 'image'}, predecessor_strided_build='/test-build')
        with ExitStack() as stack:
            terminal = stack.enter_context(patch(PREFIX + 'terminal_inputs',
                return_value=(target, {}, {'commands': 16}, 'raw-log', ())))
            raw = stack.enter_context(patch(PREFIX + 'check_strided', return_value={'commands': 16}))
            tails = stack.enter_context(patch(PREFIX + 'checked_tails', return_value={'commands': 24}))
            stack.enter_context(patch.object(gate.s, 'read_json', return_value={'build': '/test-build'}))
            stack.enter_context(patch.object(gate.s, 'digest', return_value='sha'))
            stack.enter_context(patch.object(gate.s, 'verify_pins'))
            stack.enter_context(patch.object(Path, 'read_bytes', return_value=b'gold'))
            stack.enter_context(patch.object(Path, 'read_text', return_value='rtl'))
            result = gate.prerequisites(gate.HERE, gate.HERE, target, {})
            terminal.assert_called_once()
            raw.assert_called_once_with('raw-log', 1, b'gold', 'rtl')
            tails.assert_called_once()
            self.assertEqual(len(result), 2)

    def test_strided_wrong_provenance_rejected(self):
        target = dict(kind='q4_0', accepted_image_pins={'simv': 'image'}, predecessor_strided_build='/wanted')
        with patch(PREFIX + 'terminal_inputs', return_value=(target, {}, {}, '', ())):
            with patch.object(gate.s, 'read_json', return_value={'build': '/wrong'}):
                with patch(PREFIX + 'checked_tails') as tails:
                    with self.assertRaises(ValueError):
                        gate.prerequisites(gate.HERE, gate.HERE, target, {})
                    tails.assert_not_called()

    def test_clean_cli_and_no_legacy_tail_argument(self):
        argv = [sys.executable, '-B', str(gate.HERE / 'threeway.py')]
        result = subprocess.run(argv + ['--help'], cwd='/', text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--tail-combined', result.stdout)
        self.assertIn('--preflight-only', result.stdout)
        result = subprocess.run(argv + ['--tail', '/old-timeout'], cwd='/', text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
