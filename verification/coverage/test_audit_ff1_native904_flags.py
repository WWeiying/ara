from pathlib import Path
import tempfile
import unittest

import audit_ff1_native904_flags as a


class FlagsAuditTests(unittest.TestCase):
    def test_rebuild_has_no_shell_expansion(self):
        self.assertEqual(a.rebuild_args("#!/bin/sh -e\nvcs '-top' 'ara_tb' 2>&1\n"), ['-top', 'ara_tb'])
        for text in ("vcs '$FLAGS' 2>&1", "vcs -top ara_tb; evil 2>&1", "vcs x\nevil", "other x 2>&1"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                a.rebuild_args(text)

    def test_forbidden_options_and_macros(self):
        for word in ('-pvalue+top.FPUSupport=0', '-gvalue', '-cfg', '-libmap', '-y', '+define+TARGET_GATESIM',
                     '+define+FPUSupport=0', '+define+NR_LANES=8', '+define+VLEN=512'):
            with self.subTest(word=word), self.assertRaises(ValueError):
                a.expand([word], lambda p: b'')

    def test_source_override_not_comments_or_strings(self):
        a.check_source('// defparam x.P=0;\n/* config C; */ string s="config,defparam";')
        for text in ('defparam x.P=0;', 'config c; endconfig', '`define TARGET_GATESIM', '`undef FPUSupport'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                a.check_source(text)

    def test_nested_lists_and_cycle(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            first, second = root / 'a.f', root / 'b.f'
            first.write_text('-f ' + str(second))
            second.write_text('+define+NR_LANES=4\n' + str(root / 'unit.sv'))
            sources, lists, defines, _ = a.expand(['-f', str(first)], lambda p: p.read_bytes())
            self.assertEqual(sources, [str(root / 'unit.sv')])
            self.assertEqual(lists, [str(first), str(second)])
            self.assertEqual(defines, ['NR_LANES=4'])
            second.write_text('-f ' + str(first))
            with self.assertRaises(ValueError):
                a.expand(['-f', str(first)], lambda p: p.read_bytes())

    def test_relative_lists_and_unknown_operands_fail_closed(self):
        for words in (['-f', 'relative.f'], ['-f'], ['config.map'], ['/tmp/foo.cfg']):
            with self.subTest(words=words), self.assertRaises(ValueError):
                a.expand(words, lambda p: b'')


if __name__ == '__main__':
    unittest.main()
