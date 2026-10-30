"""Fail-closed build/model gates; no simulator is started by these tests."""
from pathlib import Path
import unittest
from unittest.mock import patch

import run_strided_attention as runner


class StridedRunGate(unittest.TestCase):
    def test_build_rejects_missing_full_cost_contract(self):
        # This fails before reading a source manifest or invoking any child.
        for row in ({}, {'kind': 'q8_0', 'state': 'COMMON_ENTRY_BUILT_NOT_EXECUTED'},
                    {'kind': 'q8_0', 'state': 'STRIDED_ENTRY_BUILT_NOT_EXECUTED', 'gather_timed': False}):
            with patch.object(runner.s, 'read_json', return_value=row), self.assertRaises(ValueError):
                runner.checked_build(Path('/synthetic/build'))

    def test_model_rejects_nonterminal_or_fallback(self):
        for row in ({}, {'state': 'RUNNING'}, {'state': 'PASS', 'current_inputs_match': False}):
            with patch.object(runner.s, 'read_json', return_value=row), self.assertRaises(ValueError):
                runner.checked_model(Path('/synthetic/model'), {})
        result = dict(state='PASS', current_inputs_match=True, child_pid=None,
                      source_pins_sha256='same', log_sha256='same')
        with patch.object(runner.s, 'read_json', return_value=result), \
             patch.object(runner.s, 'digest', return_value='same'), \
             patch.object(Path, 'read_text', return_value='synthetic'), \
             patch.object(runner, 'check_model_log', return_value=dict(native_command_attempts=0)), \
             self.assertRaises(ValueError):
            runner.checked_model(Path('/synthetic/model'), {})

    def test_worker_accepts_only_same_decoder_and_visible_group(self):
        source = Path(runner.__file__).read_text()
        self.assertIn("ordinary_value_decode') == 'same RVV decoder as candidate'", source)
        self.assertIn("key_token_stride=2 * row", source)
        self.assertIn("gather_timed=True", source)
        self.assertIn("'--require-axi-write'", source)
        self.assertIn("wait_owner(prior, args.gate_owner_pid", source)


if __name__ == '__main__':
    unittest.main()
