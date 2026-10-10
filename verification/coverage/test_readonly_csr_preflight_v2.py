import os
from pathlib import Path
import unittest
import build_readonly_csr_preflight_v2 as v


class BootstrapTests(unittest.TestCase):
    def test_only_symbol_export(self):
        self.assertEqual(v.START.read_text(), v.OLD_START.read_text().replace(
            'trap_fail:\n', '.globl trap_fail\ntrap_fail:\n', 1))

    def test_exact_source_replacement(self):
        old = Path(v.frozen.__file__).read_text(); new = v.adapted_source(old)
        self.assertEqual(new.replace("'readonly_csr_start.S'", "'gap75_start.S'"), old)
        self.assertEqual(v.life.digest(Path(v.frozen.__file__)), v.FROZEN_SHA)
        self.assertEqual(v.life.digest(v.frozen.APP), v.APP_SHA)

    def test_reject_missing_extra_already_adapted(self):
        old = Path(v.frozen.__file__).read_text()
        for source in (old.replace("'gap75_start.S'", "'foreign.S'", 1),
                       old + "\n# 'gap75_start.S'\n", v.adapted_source(old)):
            with self.assertRaises(ValueError): v.adapted_source(source)

    def test_same_oracle_and_opcode_matrix(self):
        ns = v.load_adapter()
        self.assertEqual(ns['CHECKS'], 733)
        self.assertEqual(ns['CONDS'], v.frozen.CONDS); self.assertEqual(ns['LINES'], v.frozen.LINES)
        self.assertEqual([ns['opcode'](i) for i in range(12)], [v.frozen.opcode(i) for i in range(12)])

    @unittest.skipUnless(os.environ.get('RC_PREFLIGHT_V2'), 'Set RC_PREFLIGHT_V2 for sealed real fixture')
    def test_actual_serialized_artifact(self):
        out = Path(os.environ['RC_PREFLIGHT_V2'])
        pre = v.verify(out, v.life.digest(out / 'preflight-manifest.json'))
        self.assertEqual((pre['checks'], pre['validation']['exact_traps'], len(pre['targets'])), (733, 12, 24))


if __name__ == '__main__': unittest.main()
