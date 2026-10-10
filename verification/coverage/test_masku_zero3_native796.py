import copy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import masku_zero3_native796 as m


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = m.read_bound(m.REVIEW, m.REVIEW_SHA)
        cls.c = dict(instances=m.compiled(cls.review))
        cls.child = next(k for k, i in enumerate(cls.c['instances']) if i['scope'] == m.SCOPE)

    def el(self):
        i = self.c['instances'][self.child]
        return ''.join('CHECKSUM: "%s %s"\nINSTANCE: %s\nANNOTATION: "%s"\nToggle %s "logic %s[255:0]"\n' %
                       (i['design_checksum'], i['toggle_checksum'], m.SCOPE, m.ANNOTATION, n, n) for n in m.NAMES)

    def rows(self, out, index, stage, mutate=None):
        rows = []
        for k, b in enumerate(self.c['instances'][index]['bindings']):
            rows.append(dict(handle=str(k + 1), path=b['label'], meta=b['label'], name=b['label'],
                             excluded=str(int(stage in ('selected', 'reloaded') and b['role'] == 'target'))))
        if mutate: mutate(rows)
        with (out / ('native_%s_%d.tsv' % (stage, index))).open('w', newline='') as stream:
            w = csv.DictWriter(stream, fieldnames=['handle', 'path', 'meta', 'name', 'excluded'], delimiter='\t')
            w.writeheader()
            w.writerows(rows)

    def bind_fixture(self, out):
        m.save(out / 'config.json', self.c)
        for k in range(26): self.rows(out, k, 'before')
        m.bind(out, self.c)

    def test_exact987_three256_including_output(self):
        self.assertEqual(len(self.c['instances']), 26)
        self.assertEqual(sum(len(i['bindings']) for i in self.c['instances']), 987)
        targets = [b for i in self.c['instances'] for b in i['bindings'] if b['role'] == 'target']
        self.assertEqual({b['name'] for b in targets}, set(m.NAMES))
        self.assertEqual(sum(b['width'] for b in targets), 768)
        self.assertEqual(next(b for b in targets if b['name'] == 'bit_enable_mask_o')['attributes']['portnode'], '3')
        parent_alias = next(b for b in self.c['instances'][0]['bindings'] if b['name'] == 'bit_enable_mask')
        self.assertEqual(parent_alias['role'], 'protected')

    def test_five_phase_model_only_not_native_qualification(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self.bind_fixture(out)
            for stage in m.STAGES:
                (out / m.FILES[stage]).write_text(self.el() if stage in ('selected', 'reloaded') else '')
                m.check_el(out, self.c, stage)
                for k in range(26):
                    if stage != 'before': self.rows(out, k, stage)
                    m.inventory(out, self.c, stage, k)
            m.bound_selection(out)
            self.assertFalse((out / 'capture-result.json').exists())

    def test_inventory_missing_duplicate_foreign_partial_meta_handle(self):
        def renamed(rows, label): rows[0].update(name=label, path=label, meta=label)
        mutations = [lambda r: r.pop(), lambda r: r.append(dict(r[0])),
                     lambda r: renamed(r, 'foreign'), lambda r: renamed(r, 'bit_enable_mask_o[127:0]'),
                     lambda r: r[0].update(meta='other'), lambda r: r[0].update(handle='not-a-handle')]
        with tempfile.TemporaryDirectory() as td:
            for mutation in mutations:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    self.rows(Path(td), self.child, 'before', mutation)
                    m.inventory(Path(td), self.c, 'before', self.child)

    def test_partial_array_rejected(self):
        index = next(k for k, i in enumerate(self.c['instances']) if any(b['kind'] == 'arrays' for b in i['bindings']))
        obj = next(b for b in self.c['instances'][index]['bindings'] if b['kind'] == 'arrays')
        def mutation(rows):
            row = next(r for r in rows if r['name'] == obj['label'])
            row.update(name=obj['name'] + '[0]', path=obj['name'] + '[0]', meta=obj['name'] + '[0]')
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self.rows(out, index, 'before', mutation)
            with self.assertRaises(ValueError): m.inventory(out, self.c, 'before', index)

    def test_all_targets_required_each_phase_and_complement_protected(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self.bind_fixture(out)
            for stage in m.STAGES:
                for name in m.NAMES:
                    def mutation(rows):
                        row = next(r for r in rows if r['name'] == name + '[255:0]')
                        row['excluded'] = '0' if stage in ('selected', 'reloaded') else '1'
                    self.rows(out, self.child, stage, mutation)
                    with self.subTest(stage=stage, name=name), self.assertRaises(ValueError):
                        m.inventory(out, self.c, stage, self.child)
            for index in range(26):
                obj = next(b for b in self.c['instances'][index]['bindings'] if b['role'] == 'protected')
                def mutation(rows): next(r for r in rows if r['name'] == obj['label'])['excluded'] = '1'
                self.rows(out, index, 'selected', mutation)
                with self.subTest(index=index), self.assertRaises(ValueError):
                    m.inventory(out, self.c, 'selected', index)

    def test_native_identity_and_binding_selection_drift(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            self.bind_fixture(out)
            with (out / 'actual-selection.tcl').open('a') as stream: stream.write('set extra 1\n')
            with self.assertRaises(ValueError): m.bound_selection(out)
            self.rows(out, self.child, 'selected')
            with (out / ('native_before_%d.tsv' % self.child)).open('a') as stream: stream.write('\n')
            with self.assertRaises(ValueError): m.inventory(out, self.c, 'selected', self.child)
            with self.assertRaises(ValueError): m.bind(out, self.c)

    def test_el_exact_three_order_independent(self):
        self.assertEqual(len(m.records(self.el(), self.c)), 3)
        blocks = self.el().splitlines()
        self.assertEqual(m.records('\n'.join(blocks[8:] + blocks[4:8] + blocks[:4]), self.c),
                         m.records(self.el(), self.c))

    def test_el_negative_checksum_scope_metric_direction_width_port_parent(self):
        good = self.el()
        mutations = [good.replace('1400516067', '1'), good.replace('4132557224', '1'),
                     good.replace(m.SCOPE, m.PARENT), good.replace('Toggle ', 'Line '),
                     good.replace('Toggle ', 'Toggle 0to1 '), good.replace('Toggle ', 'Toggle 1to0 '),
                     good.replace('[255:0]', '[127:0]'), good.replace('logic ', 'wire '),
                     good.replace('bit_enable_mask_o', 'bit_enable_mask'),
                     good.replace(m.ANNOTATION, 'parent alias qualification'),
                     good + good[:good.index('Toggle ')], good + 'Branch foreign\n',
                     '\n'.join(good.splitlines()[:8]), good.replace('Toggle bit_enable_mask_o ', 'Toggle bit_enable_mask_o [0] ')]
        for text in mutations:
            with self.subTest(text=text), self.assertRaises(ValueError): m.records(text, self.c)

    def test_empty_phases_reject_global_waiver(self):
        with tempfile.TemporaryDirectory() as td:
            for stage in ('before', 'reset', 'final'):
                out = Path(td)
                (out / m.FILES[stage]).write_text(self.el())
                with self.assertRaises(ValueError): m.check_el(out, self.c, stage)

    def test_scope_index_and_stage_rejected(self):
        for stage, index in [('other', 0), ('before', -1), ('before', 26)]:
            with self.assertRaises(ValueError): m.inventory(Path('/unused'), self.c, stage, index)

    def test_compiled_source_or_object_drift(self):
        bad = copy.deepcopy(self.review)
        bad['objects'][0]['compiled_attributes']['left'] = '511'
        with self.assertRaises(ValueError): m.compiled(bad)
        bad = copy.deepcopy(self.review)
        bad['objects'][0]['compiled_attributes']['portnode'] = '0'
        with self.assertRaises(ValueError): m.compiled(bad)
        bad = copy.deepcopy(self.review)
        bad['module_checksum'] = '1'
        with self.assertRaises(ValueError): m.compiled(bad)

    def test_no_native_done_only_qualification(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            m.save(out / 'terminal.json', dict(returncode=0, timeout=False, actual_dve=[]))
            m.save(out / 'execution.json', {})
            m.save(out / 'live-identity.json', [])
            with patch.object(m, 'verify', return_value=self.c):
                with self.assertRaises(ValueError): m.inspect(out, 'model-only')
            self.assertFalse((out / 'capture-result.json').exists())

    def test_tcl_five_phase_model_no_eda(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            (out / 'DVEfiles').mkdir()
            c = dict(self.c, design='/frozen/design.vdb', sample='/admitted/sample.vdb',
                     test='/admitted/sample/test', python='/sealed/python', helper=str(Path(m.__file__).resolve()))
            (out / 'selection.tcl').write_text(m.selection(c))
            (out / 'actual-selection.tcl').write_text(''.join('set ::re_targets(%d) [list %s]\n' %
                (k, ' '.join(m.atom(n + '[255:0]') for n in m.NAMES) if k == self.child else '') for k in range(26)))
            (out / 'DVEfiles/dve_gui.log').write_text("The design '/frozen/design.vdb' was loaded successfully.\n")
            host = r'''
set ::re_test_only 1
set ::env(DVE_COVERAGE_OUTPUT) {%s}
eval [list source {%s}]
set ::events {}
proc gui_open_cov {args} {}
proc p740_root {} {}
proc gui_list_action {args} {}
proc dw_select {args} {}
proc gui_exclude_items {args} {lappend ::events apply}
proc gui_exclusion {args} {}
proc dw_save {args} {}
proc dw_reset {} {lappend ::events resetcall}
proc dw_load {args} {lappend ::events load}
proc re_inventory {stage} {lappend ::events $stage}
proc re_call {args} {return MODEL_ONLY}
re_session
puts [join $::events ,]
''' % (out, m.ENTRY)
            result = subprocess.run(['tclsh'], input=host, text=True, capture_output=True, check=True)
            self.assertEqual(result.stderr, '')
            self.assertIn('before,apply,apply,apply,selected,resetcall,reset,load,reloaded,resetcall,final', result.stdout)


if __name__ == '__main__': unittest.main()
