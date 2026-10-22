import copy
import csv
import io
import json
import unittest
from unittest.mock import patch

import mfpu272_five_phase as tool


class FivePhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = json.loads(tool.BINDING.read_bytes())
        cls.original = json.loads((tool.old.RUN / 'config.json').read_bytes())
        cls.c = dict(bound=cls.q['instances'], compiled=cls.original['instances'],
                     identity=cls.original['identity'], output='/tmp/exact-mfpu-test',
                     **{k: cls.original[k] for k in ('design', 'vdb', 'test')})
        cls.text = (tool.old.RUN / 'native_before_0.tsv').read_text()
        cls.el = tool.Path(cls.q['proposed_EL']).read_text()

    def test_actual_paired_el(self):
        self.assertEqual(len(tool.el_members(self.el, self.c)), 34816)

    def test_foreign_annotation_and_header_rejected(self):
        for text in (self.el.replace(tool.ANNOTATION, 'foreign'),
                     self.el + 'CHECKSUM: "0 0"\nINSTANCE: ' + self.c['bound'][0]['scope'] + '\n',
                     self.el.replace('ANNOTATION:', '// removed:')):
            with self.assertRaises(ValueError): tool.el_members(text, self.c)

    def test_missing_direction_and_extra_protected_rejected(self):
        for text in (self.el.replace('Toggle 1to0 fmt_outputs[3].result [0]\n', '', 1),
                     self.el + 'Toggle 0to1 foreign_control [0]\n'):
            with self.assertRaises(ValueError): tool.el_members(text, self.c)

    def test_actual_typed_before_and_reset(self):
        for stage in ('before', 'reset', 'final'):
            tool.compare_stage(self.c['compiled'][0], self.c['bound'][0], self.text, stage)

    def test_protected_coverage_and_role_rejected(self):
        rows = list(csv.DictReader(io.StringIO(self.text), delimiter='\t'))
        target = {s['native_label'] for s in self.c['bound'][0]['signals']}
        pos = next(i for i, r in enumerate(rows) if r['name'] not in target)
        for key, value in [('coverage', 'Excluded'), ('type', 'unknown')]:
            changed = copy.deepcopy(rows); changed[pos][key] = value
            out = io.StringIO(); writer = csv.DictWriter(out, fieldnames=changed[0], delimiter='\t')
            writer.writeheader(); writer.writerows(changed)
            with self.assertRaises(ValueError):
                tool.compare_stage(self.c['compiled'][0], self.c['bound'][0], out.getvalue(), 'applied')

    def test_missing_native_child_rejected(self):
        lines = self.text.splitlines(keepends=True)
        with self.assertRaises(ValueError):
            tool.compare_stage(self.c['compiled'][0], self.c['bound'][0], ''.join(lines[:1] + lines[2:]), 'final')

    def test_flags_all_stages_exact(self):
        rows = [dict(stage=s, scope=i['scope'], label=t['native_label'],
                     excluded='1' if s in ('applied', 'reloaded') else '0')
                for s in tool.STAGES for i in self.c['bound'] for t in i['signals']]
        tool.flags_gate(rows, self.c['bound'])
        self.assertEqual(len(rows), 1360)
        for changed in (rows[:-1], [dict(rows[0], excluded='1'), *rows[1:]], list(reversed(rows))):
            with self.assertRaises(ValueError): tool.flags_gate(changed, self.c['bound'])

    def test_native_terminal_gate(self):
        live = [dict(pid=123, exe=self.c['identity']['executable'], cwd=self.c['output'])]
        terminal = dict(returncode=0, timeout=False, actual_dve=live)
        tool.terminal_gate(terminal, self.c, live)
        for changed in (dict(terminal, returncode=1), dict(terminal, timeout=True),
                        dict(terminal, actual_dve=[])):
            with self.assertRaises(ValueError): tool.terminal_gate(changed, self.c, live)

    def test_missing_receipt_hold(self):
        with patch.object(tool, 'BINDING_SHA', '0' * 64):
            with self.assertRaises(ValueError): tool.origin()

    def test_actual_generated_full_entry(self):
        selection = ''.join('set mq_%s {%s}\n' % (k, self.c[k]) for k in ('design', 'vdb', 'test'))
        selection += 'set mq_instances [list ' + ' '.join(
            '[list {%s} [list %s]]' % (i['scope'], ' '.join('{%s}' % t['native_label'] for t in i['signals']))
            for i in self.c['bound']) + ']\n'
        result = tool.host_hook(self.c, selection)
        self.assertEqual(result['inventories'], 3940)
        self.assertFalse(result['EDA_launched'])


if __name__ == '__main__': unittest.main()
