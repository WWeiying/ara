import copy
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import run_balanced_sdk as b


class BalancedSdkRunner(unittest.TestCase):
    def test_original_frozen_program_contract_and_exact_elf(self):
        for kind, (root, name, sha, state, commands, outputs) in b.PROGRAMS_BY_KIND.items():
            self.assertEqual(b.digest(root / name), sha)
            record = json.loads((root / name).read_text())
            b.program_contract(record, kind, state, commands, outputs)
            self.assertEqual(b.digest(record['elf']), record['elf_sha256'])
            self.assertTrue(b.elf_admission(Path(record['elf']).read_bytes(), 32))
            for key, value in (('trials', 2), ('m', 1), ('preparation_included', False),
                               ('cold_weight_repack_included', True), ('whole_model', True),
                               ('n', 64), ('k', 256), ('outputs', outputs - 1)):
                bad = copy.deepcopy(record)
                bad[key] = value
                with self.subTest(kind=kind, key=key), self.assertRaises(ValueError):
                    b.program_contract(bad, kind, state, commands, outputs)

    def test_cannot_start_simulation_without_review(self):
        with tempfile.TemporaryDirectory() as root, patch.object(b.subprocess, 'Popen') as child:
            args = types.SimpleNamespace(output=Path(root) / 'run', execute_reviewed=False, timeout=10)
            with self.assertRaises(ValueError):
                b.run(args)
            child.assert_not_called()

    def test_original_128bit_ffn_cannot_be_used_as_matched_baseline(self):
        with self.assertRaises(ValueError):
            b.inputs('ffn', 0, b.RUNS / 'e2e_physical_wide_soc128_20261106_01',
                     'c0b7dbe24f03583851d64146da5bbac06341b9f24a70d0036e3aea0294f1a195', None, None)

    def test_both_oracles_retain_exact_shapes(self):
        qkv = b.PROGRAMS_BY_KIND['prefill'][0]
        self.assertEqual(list(map(len, b.oracle(qkv, 'prefill'))), [32768, 16384, 16384])
        ffn = b.oracle(b.PROGRAMS_BY_KIND['ffn'][0], 'ffn')
        self.assertEqual(list(map(len, ffn[0])), [2048] * 3)
        self.assertEqual(list(map(len, ffn[1])), [9344, 28032])
        self.assertEqual(ffn[2], [1, 1, 2])


if __name__ == '__main__':
    unittest.main()
