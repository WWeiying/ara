from pathlib import Path
import unittest
from unittest.mock import patch

import run_tail_attention as worker


class TailRun(unittest.TestCase):
    def test_reject_incompatible_build(self):
        for document in ({}, {'state': 'STRIDED_ENTRY_BUILT_NOT_EXECUTED'},
                         {'state': 'TAIL_ENTRY_BUILT_NOT_EXECUTED', 'kind': 'q8_0', 'performance': True}):
            with patch.object(worker.s, 'read_json', return_value=document), self.assertRaises(ValueError):
                worker.checked_build(Path('/synthetic/build'))

    def test_actual_oracle_identity_and_binding(self):
        pins = {}
        oracle = worker.oracle_inputs(pins)
        self.assertTrue(callable(oracle))
        self.assertTrue(any(path.endswith('/host_score.so') for path in pins))

    def test_protocol_and_exact_reference_remain_required(self):
        source = Path(worker.__file__).read_text()
        self.assertIn("'--require-axi-write'", source)
        self.assertIn('key.read_bytes(), oracle)', source)
        self.assertIn("identity()", source)
        self.assertIn('checked_model(prior, pins)', source)


if __name__ == '__main__':
    unittest.main()
