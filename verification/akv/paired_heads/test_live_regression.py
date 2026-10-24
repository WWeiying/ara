#!/usr/bin/env python3
"""Historical source resolution is explicit; all other drift must fail closed."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import build_live_regression as b


class HistoricalInputTest(unittest.TestCase):
    def test_only_reviewed_runtime_sources_resolve_to_snapshots(self):
        with tempfile.TemporaryDirectory(prefix='akv-history-test-') as temp:
            root = Path(temp)
            base,backup = root/'base',root/'backup'
            base.mkdir(); backup.mkdir()
            c,asm,other = root/'runtime.c',root/'runtime.S',root/'input.bin'
            c.write_text('promoted C'); asm.write_text('promoted S'); other.write_bytes(b'data')
            before_c,before_asm = backup/'native-before.c',backup/'attention-before.S'
            before_c.write_text('original C'); before_asm.write_text('original S')
            pins = {str(c):b.s.digest(before_c),str(asm):b.s.digest(before_asm),str(other):b.s.digest(other)}
            b.s.atomic_json(base/'source-pins.json',pins)
            report = dict(state='BUILT_NOT_EXECUTED',post_pins_match=True,
                source_pins_sha256=b.s.digest(base/'source-pins.json'),artifact_sha256={})
            (base/'build.json').write_text('{}')
            with mock.patch.multiple(b,CANONICAL=c,ASSEMBLY=asm,BACKUP=backup):
                resolved,aliases = b.historical_pins(base,report)
                self.assertNotIn(str(c),resolved)
                self.assertIn(str(before_c),resolved)
                self.assertEqual(aliases[str(asm)]['snapshot'],str(before_asm))
                other.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    b.historical_pins(base,report)
                other.write_bytes(b'data'); before_c.write_text('changed backup')
                with self.assertRaises(ValueError):
                    b.historical_pins(base,report)


if __name__ == '__main__':
    unittest.main()
