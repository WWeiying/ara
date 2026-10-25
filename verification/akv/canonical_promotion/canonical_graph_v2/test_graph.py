import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import graph as g


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a, self.b = self.root / 'a', self.root / 'b'
        self.a.mkdir(); self.b.mkdir()
        (self.a / 'one.svh').write_text('`define ONE 1\n')
        (self.b / 'two.svh').write_text('`define TWO 2\n')
        self.source = self.root / 'source.sv'
        self.source.write_text('`include "one.svh"\nmodule source; endmodule\n')
        self.before = '\n'.join(['+define+FIRST=1', '+define+SECOND=2',
            '+incdir+' + str(self.a), '+incdir+' + str(self.b), str(self.source)])
        self.after = '\n'.join(['', '+define+SECOND=2', '+define+FIRST=1',
            '+incdir+' + str(self.b), '+incdir+' + str(self.a), str(self.source), ''])

    def test_proven_ordering_and_whitespace_only(self):
        report = g.prove(self.before, self.after)
        self.assertTrue(report['source_order_equal'])
        self.assertEqual(report['sources'], 1)
        self.assertEqual(report['include_directories'], 2)
        self.assertEqual(len(report['header_pins']), 2)

    def test_token_value_addition_or_deletion_rejected(self):
        for text in (self.after.replace('SECOND=2', 'SECOND=3'),
                     self.after + '\n+define+EXTRA', self.after.replace('+define+FIRST=1\n', '')):
            with self.assertRaisesRegex(ValueError, 'token inventory'):
                g.prove(self.before, text)

    def test_same_tokens_moved_after_source_rejected(self):
        lines = g.base.tokens(self.after)
        lines.append(lines.pop(0))
        with self.assertRaisesRegex(ValueError, 'effective macro'):
            g.prove(self.before, '\n'.join(lines))

    def test_source_order_change_rejected(self):
        other = self.root / 'other.sv'
        other.write_text('module other; endmodule')
        with self.assertRaisesRegex(ValueError, 'Source order'):
            g.prove(self.before + '\n' + str(other),
                    self.after.replace(str(self.source), str(other) + '\n' + str(self.source)))

    def test_include_name_collision_rejected(self):
        (self.b / 'one.svh').write_text('`define ONE 999\n')
        with self.assertRaisesRegex(ValueError, 'header selection'):
            g.prove(self.before, self.after)

    def test_dynamic_and_parent_relative_includes_rejected(self):
        for text in ('`include `HEADER\n', '`include "../one.svh"\n'):
            self.source.write_text(text)
            with self.assertRaisesRegex(ValueError, 'separate review'):
                g.prove(self.before, self.after)

    def test_conflicting_macro_values_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting macro'):
            g.prove(self.before + '\n+define+FIRST=2', self.after + '\n+define+FIRST=2')

    def test_real_current_template_and_inventory(self):
        expected = g.expected_graph(g.base.OLD_LIST.read_text())
        self.assertEqual(expected, g.base.tokens(g.TEMPLATE.read_text()))
        report = g.prove('\n'.join(g.base.expected_graph(g.base.OLD_LIST.read_text())),
                         g.TEMPLATE.read_text())
        self.assertEqual((report['sources'], report['tokens'], report['include_directories']),
                         (439, 977, 7))
        g.base.verify(g.inputs())

    def test_unreviewed_template_rejected(self):
        path = self.root / 'template.f'
        path.write_text(self.after)
        with patch.object(g, 'TEMPLATE', path), self.assertRaisesRegex(ValueError, 'Unreviewed'):
            g.expected_graph(g.base.OLD_LIST.read_text())


if __name__ == '__main__':
    unittest.main()
