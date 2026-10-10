import os
from pathlib import Path
import struct
import unittest
import build_readonly_csr_preflight_v3 as v
from test_readonly_csr_preflight import fixture


def elf(words):
    code = b''.join(struct.pack('<I', w) for w in words)
    blob = bytearray(128 + 64 + len(code)); blob[:6] = b'\x7fELF\x02\x01'
    struct.pack_into('<HHIQQQIHHHHHH', blob, 16, 2, 243, 1, 0, 0, 128, 0, 64, 0, 0, 64, 1, 0)
    struct.pack_into('<IIQQQQIIQQ', blob, 128, 0, 1, 4, 0x80002000, 192, len(code), 0, 0, 4, 0)
    blob[192:] = code; return bytes(blob)


WORDS = [0x0002f057, 0x02000407, 0x02000507, 0xc0047057, 0x0281b557,
         0x0002f057, 0x02000427, 0x02000527]


class RodataTests(unittest.TestCase):
    def test_exact_three_storage_changes(self):
        self.assertEqual(v.APP.read_text(), v.expected_app(v.frozen.APP.read_text()))
        self.assertEqual(v.life.digest(v.APP), v.APP_SHA)

    def test_missing_table_rejected(self):
        with self.assertRaises(ValueError): v.expected_app(v.APP.read_text())

    def test_only_eight_explicit_vectors(self): v.verify_vector_code(elf(WORDS))

    def test_actual_implicit_vector_failure_rejected(self):
        with self.assertRaises(ValueError): v.verify_vector_code((v.FAILED / 'input.elf').read_bytes())

    def test_extra_wrong_vector_configuration(self):
        for words in (WORDS + [0x5e003657], [0xcda47057] + WORDS[1:]):
            with self.assertRaises(ValueError): v.verify_vector_code(elf(words))

    def test_oracle_unchanged(self):
        rows, symbols, trace = fixture(); ns = v.load_adapter()
        self.assertEqual(ns['validate'](rows, symbols, trace), v.frozen.validate(rows, symbols, trace))
        self.assertEqual(ns['APP'], v.APP)

    @unittest.skipUnless(os.environ.get('RC_PREFLIGHT_V3'), 'Set RC_PREFLIGHT_V3 for actual serialized replay')
    def test_actual_serialized_preflight(self):
        out = Path(os.environ['RC_PREFLIGHT_V3'])
        pre = v.verify(out, v.life.digest(out / 'preflight-manifest.json'))
        self.assertEqual((pre['validation']['exact_traps'], pre['checks'], len(pre['targets'])), (12, 733, 24))


if __name__ == '__main__': unittest.main()
