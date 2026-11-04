#!/usr/bin/env python3
"""Small tests of evidence integrity and failure detection, without EDA calls."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

import run_shared_alu as flow


class AluFlowTest(unittest.TestCase):
    def test_frozen_input_identity(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            source = out/'source.sv'
            source.write_text('module original; endmodule\n')
            flow.save(out/'manifest.json', {'hashes': {'source.sv': flow.sha(source)}})
            flow.verify(out)
            source.write_text('module changed; endmodule\n')
            with self.assertRaisesRegex(RuntimeError, 'Frozen input changed'):
                flow.verify(out)

    def test_fatal_even_with_zero_process_exit(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            with self.assertRaisesRegex(RuntimeError, 'Command failed'):
                flow.command([sys.executable, '-c', "print('Fatal: mismatch')"],
                             out, out/'run.log', seconds=10)

    def test_vcs_compile_error(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            with self.assertRaisesRegex(RuntimeError, 'Command failed'):
                flow.command([sys.executable, '-c', "print('Error-[SE] Syntax error')"],
                             out, out/'compile.log', seconds=10)

    def test_requires_completion_marker(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            with self.assertRaisesRegex(RuntimeError, 'Missing completion marker'):
                flow.command([sys.executable, '-c', "print('partial result')"],
                             out, out/'run.log', 'SHARED_ALU_PASS', seconds=10)

    def test_successful_marker(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            flow.command([sys.executable, '-c', "print('SHARED_ALU_PASS')"],
                         out, out/'run.log', 'SHARED_ALU_PASS', seconds=10)

    def test_atomic_status(self):
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            flow.save(out/'status.json', {'state': 'RUNNING'})
            flow.save(out/'status.json', {'state': 'PASS'})
            self.assertEqual(json.loads((out/'status.json').read_text())['state'], 'PASS')
            self.assertFalse((out/'status.tmp').exists())


if __name__ == '__main__':
    unittest.main()
