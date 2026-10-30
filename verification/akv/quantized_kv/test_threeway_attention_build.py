"""Successor command policy; no simulator is launched by these tests."""
from pathlib import Path
import unittest

import build_threeway_attention as b


class ThreewayBuildTest(unittest.TestCase):
    def commands(self):
        base = Path('/example/build')
        cc = ['/tools/riscv64-unknown-elf-gcc', '-c', str(b.predecessor.MAIN),
              '-o', str(base/'main.o'), '-ffp-contract=fast', '-fno-fast-math',
              '-Werror', '-march=rv64gcv_zfh_zvfh']
        link = ['cc', '-nostdlib', str(base/'main.o'), '-Wl,--gc-sections',
                '-Wl,-Map=/example/old.map', '-o', '/example/old.elf']
        return base, cc, link

    def test_original_flags_preserved(self):
        base, cc, link = self.commands()
        self.assertEqual(b.templates([dict(argv=cc), dict(argv=link)], base), (cc, link))
        for before, after in (('-ffp-contract=fast', '-ffp-contract=off'),
                              ('-fno-fast-math', '-ffast-math'), ('-Werror', '-w'),
                              ('-march=rv64gcv_zfh_zvfh', '-march=rv64gcv')):
            bad = [after if x == before else x for x in cc]
            with self.assertRaises(ValueError):
                b.templates([dict(argv=bad), dict(argv=link)], base)
        with self.assertRaises(ValueError):
            b.templates([dict(argv=cc), dict(argv=cc), dict(argv=link)], base)

    def test_measurement_and_no_architectural_changes(self):
        source = b.MAIN.read_text()
        self.assertIn('#include "threeway_strided_primitives.h"', source)
        self.assertEqual((b.HERE/'threeway_strided_primitives.h').read_text(),
                         b.predecessor.MAIN.read_text().split('int main(void) {', 1)[0])
        self.assertIn('MODE_QBS,\n                          MODE_QBS,MODE_SHARED_RVV,MODE_HEAD_MAJOR', source)
        start = source.index('const uint64_t start=strided_cycles();')
        end = source.index('const uint64_t elapsed=strided_cycles()-start;')
        window = source[start:end]
        for name in ('akv_quant_ggml_map(', 'akv_quant_strided_execute(',
                     'akv_quant_online_shared(', 'akv_quant_online_head_major(', 'threeway_quantize('):
            self.assertIn(name, window)
        self.assertTrue(window.rstrip().endswith('drain();'))
        self.assertIn('if (mode!=MODE_QBS) errors+=bits(y)!=bits(baseline[head][d]);', source)
        self.assertIn('fc!=baseline_fcsr', source)
        self.assertNotIn('THREEWAY_INIT_RVV_CONTEXT', source)
        self.assertNotIn('THREEWAY_READ_RVV_COUNTS', source)


if __name__ == '__main__':
    unittest.main()
