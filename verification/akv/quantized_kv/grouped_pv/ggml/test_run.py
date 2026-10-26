import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run


class WorkerContracts(unittest.TestCase):
    def test_actual_external_successor_snapshot(self):
        pins = run.external_inputs()
        snapshot = json.loads((run.HERE / 'external_snapshot.json').read_text())
        for name, sha in snapshot['source_sha256'].items():
            self.assertEqual(pins[str(run.LLAMA / name)], sha)
        self.assertGreater(len(pins), 1000)

    def test_external_drift_fails_closed(self):
        snapshot = json.loads((run.HERE / 'external_snapshot.json').read_text())
        snapshot['tree_sha256'] = '0' * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'snapshot.json'
            path.write_text(json.dumps(snapshot))
            with self.assertRaisesRegex(ValueError, 'tree differs'):
                run.external_inputs(snapshot=path)

    def commands(self):
        runtime = run.ROOT / 'software/akv/experimental/quantized_kv/runtime_strided.c'
        files = [run.LLAMA / 'ggml/src/ggml-cpu/arch/riscv' / name for name in
                 ('quant-kv.cpp', 'qbs.cpp', 'akv.cpp')]
        files.extend([run.HERE / 'test.cpp', runtime])
        rows = []
        for source in files:
            flags = ['g++', '-march=rv64gcv_zfh_zvfh', '-DGGML_USE_RISCV_QUANT_KV']
            if source.name == 'quant-kv.cpp' or source == runtime:
                flags.extend(['-fno-fast-math', '-ffp-contract=fast'])
            if source == run.HERE / 'test.cpp':
                flags.extend(['-DNDEBUG', '-UNDEBUG', '-fno-fast-math', '-ffp-contract=off'])
            rows.append(dict(directory=str(run.ROOT), file=str(source), arguments=flags))
        return rows

    def check_commands(self, rows):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            (build / 'compile_commands.json').write_text(json.dumps(rows))
            run.check_compile_sources(build)

    def test_compile_contract(self):
        self.check_commands(self.commands())

    def test_compile_missing_duplicate_and_unsafe(self):
        rows = self.commands()
        for bad in (rows[:-1], rows + [rows[0]]):
            with self.assertRaises(ValueError):
                self.check_commands(bad)
        for flag in ('-ffast-math', '-Ofast', '-ffp-contract=off'):
            bad = self.commands()
            bad[0]['arguments'].append(flag)
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.check_commands(bad)

    def test_compile_assertions_and_target(self):
        bad = self.commands()
        bad[-2]['arguments'].append('-DNDEBUG')
        with self.assertRaises(ValueError):
            self.check_commands(bad)
        bad = self.commands()
        bad[0]['arguments'][1] = '-march=rv64gc'
        with self.assertRaises(ValueError):
            self.check_commands(bad)

    def test_cmake_root(self):
        self.assertEqual((run.HERE / '../../../../..').resolve(), run.ROOT)
        self.assertIn('${CMAKE_CURRENT_LIST_DIR}/../../../../..',
                      (run.HERE / 'CMakeLists.txt').read_text())


if __name__ == '__main__':
    unittest.main()
