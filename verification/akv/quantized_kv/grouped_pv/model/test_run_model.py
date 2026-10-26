"""Read-only real graph replay plus closed prerequisite/snapshot mutations."""
from pathlib import Path
import unittest
from unittest.mock import patch

import run_model as runner


class WorkerAdmission(unittest.TestCase):
    def test_actual_graph02_pins_and_raw_replay(self):
        gate = Path(runner.json_file(runner.HERE / 'graph_receipt.json')['path'])
        pins = runner.prerequisite(gate)
        self.assertIn(str(runner.GRAPH / 'check.py'), pins)
        self.assertIn(str(gate / 'qemu.log'), pins)

    def test_actual_model_source_snapshot(self):
        pins = runner.model_inputs()
        self.assertIn(str(runner.LLAMA / 'src/llama-context.cpp'), pins)
        self.assertIn(str(runner.LLAMA / 'ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp'), pins)

    def test_wrong_gate_and_snapshot_reject(self):
        with self.assertRaises(ValueError):
            runner.prerequisite(Path('/wrong/gate'))
        original = runner.json_file
        snapshot = original(runner.HERE / 'external_snapshot.json')
        with patch.object(runner, 'json_file', return_value=dict(snapshot, tree_sha256='0' * 64)):
            with self.assertRaises(ValueError):
                runner.model_inputs()

    def test_receipt_status_and_raw_disagreement_reject(self):
        original = runner.json_file
        gate = Path(original(runner.HERE / 'graph_receipt.json')['path'])
        for filename, change in (('status.json', {'state': 'RUNNING'}),
                                 ('status.json', {'child_pid': 1}),
                                 ('result.json', {'native_calls': 31}),
                                 ('result.json', {'key_bytes': 0}),
                                 ('result.json', {'elf_sha256': 'not-pinned'}),
                                 ('result.json', {'current_inputs_match': False})):
            def documents(path):
                data = original(path)
                return dict(data, **change) if path == gate / filename else data
            with self.subTest(change=change), patch.object(runner, 'json_file', side_effect=documents), \
                 patch.object(runner, 'check_pins'), self.assertRaises(ValueError):
                runner.prerequisite(gate)

    def test_cmake_uses_own_test_and_root(self):
        cmake = (runner.HERE / 'CMakeLists.txt').read_text()
        self.assertEqual((runner.HERE / '../../../../..').resolve(), runner.ROOT)
        self.assertIn('${CMAKE_CURRENT_LIST_DIR}/../../../../..', cmake)
        self.assertIn('add_executable(quant-kv-model-grouped test.cpp)', cmake)


if __name__ == '__main__':
    unittest.main()
