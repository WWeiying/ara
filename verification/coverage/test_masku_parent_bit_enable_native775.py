import copy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import masku_parent_bit_enable_native775 as m


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = m.life.read_bound(m.source.REPORT, m.REVIEW_SHA)
        cls.c = dict(instances=m.compiled(cls.review))

    def fixture_el(self):
        i = self.c['instances'][0]
        return '\n'.join(['CHECKSUM: "%s %s"' % (i['design_checksum'], i['toggle_checksum']),
            'INSTANCE: ' + m.source.SCOPE, 'ANNOTATION: "' + m.ANNOTATION + '"',
            'Toggle bit_enable_mask "logic bit_enable_mask[255:0]"']) + '\n'

    def write_rows(self, out, index, stage, mutation=None):
        rows = []
        for k, b in enumerate(self.c['instances'][index]['bindings']):
            label = b['label']
            rows.append(dict(handle=str(k + 1), path=label, meta=label, name=label,
                             excluded=str(int(stage in ('selected', 'reloaded') and b['role'] == 'target'))))
        if mutation:
            mutation(rows)
        with (out / ('native_%s_%d.tsv' % (stage, index))).open('w', newline='') as stream:
            w = csv.DictWriter(stream, fieldnames=['handle', 'path', 'meta', 'name', 'excluded'], delimiter='\t')
            w.writeheader(); w.writerows(rows)

    def test_exact_compiled_partition(self):
        self.assertEqual(len(self.c['instances']), 26)
        self.assertEqual(sum(len(i['bindings']) for i in self.c['instances']), 987)
        targets = [(i['scope'], b['name']) for i in self.c['instances'] for b in i['bindings'] if b['role'] == 'target']
        self.assertEqual(targets, [(m.source.SCOPE, 'bit_enable_mask')])
        port = next(b for i in self.c['instances'] if i['scope'] == m.source.prior.SCOPE
                    for b in i['bindings'] if b['name'] == 'bit_enable_mask_o')
        self.assertEqual((port['role'], port['attributes']['portnode']), ('protected', '3'))

    def test_full_model_five_stages_no_native_claim(self):
        with tempfile.TemporaryDirectory(dir=m.source.OUT) as td:
            out = Path(td); m.life.save(out / 'config.json', self.c)
            for k in range(26): self.write_rows(out, k, 'before')
            m.bind(out, self.c)
            for stage in m.STAGES:
                for k in range(26):
                    if stage != 'before': self.write_rows(out, k, stage)
                    m.inventory(out, self.c, stage, k)
            self.assertEqual(json.loads((out / 'actual-binding.json').read_bytes())['protected'], 986)

    def test_inventory_missing_duplicate_foreign(self):
        mutations = [lambda r: r.pop(), lambda r: r.append(dict(r[0])),
                     lambda r: r[0].update(name='foreign'), lambda r: r[0].update(meta='other')]
        with tempfile.TemporaryDirectory(dir=m.source.OUT) as td:
            out = Path(td)
            for mutate in mutations:
                self.write_rows(out, 0, 'before', mutate)
                with self.assertRaises(ValueError): m.inventory(out, self.c, 'before', 0)

    def test_array_partial_and_port_guard(self):
        with tempfile.TemporaryDirectory(dir=m.source.OUT) as td:
            out = Path(td)
            def partial(rows):
                obj = next(b for b in self.c['instances'][0]['bindings'] if b['kind'] == 'arrays')
                row = next(r for r in rows if r['name'] == obj['label'])
                row.update(name=obj['name'] + '[0]', path=obj['name'] + '[0]', meta=obj['name'] + '[0]')
            self.write_rows(out, 0, 'before', partial)
            with self.assertRaises(ValueError): m.inventory(out, self.c, 'before', 0)
            child = next(k for k, i in enumerate(self.c['instances']) if i['scope'] == m.source.prior.SCOPE)
            def port(rows):
                next(r for r in rows if r['name'] == 'bit_enable_mask_o[255:0]')['excluded'] = '1'
            self.write_rows(out, child, 'selected', port)
            with self.assertRaises(ValueError): m.inventory(out, self.c, 'selected', child)

    def test_startup_flag_rejected(self):
        with tempfile.TemporaryDirectory(dir=m.source.OUT) as td:
            out = Path(td)
            def exclude(rows):
                next(r for r in rows if r['name'] == 'bit_enable_mask[255:0]')['excluded'] = '1'
            self.write_rows(out, 0, 'before', exclude)
            with self.assertRaises(ValueError): m.inventory(out, self.c, 'before', 0)

    def test_el_exact(self):
        self.assertEqual(len(m.records(self.fixture_el(), self.c)), 1)

    def test_el_negatives(self):
        good = self.fixture_el()
        bad = [good.replace('Toggle ', 'Line '), good + good.splitlines()[-1] + '\n',
               good.replace('[255:0]', '[127:0]'), good.replace('Toggle bit_enable_mask ', 'Toggle 0to1 bit_enable_mask '),
               good.replace('Toggle bit_enable_mask ', 'Toggle bit_enable_mask [0] '),
               good.replace('bit_enable_mask', 'bit_enable_mask_o'), good.replace(m.source.SCOPE, m.source.prior.SCOPE),
               good.replace('2088425441', '1'), good + 'ANNOTATION: "' + m.ANNOTATION + '"\n',
               good.replace('logic bit_enable_mask', 'wire bit_enable_mask'), good.replace(m.ANNOTATION, 'other')]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ValueError): m.records(text, self.c)

    def test_existing_el_overlap(self):
        self.assertEqual(m.no_overlap(''), [])
        self.assertTrue(m.no_overlap(self.fixture_el().replace('bit_enable_mask', 'other')))
        for text in [self.fixture_el(), self.fixture_el().replace('bit_enable_mask "', 'bit_enable_mask [0] "'),
                     'CHECKSUM: "1"\nINSTANCE:' + m.source.SCOPE + '\n',
                     'CHECKSUM: "1"\nINSTANCE:' + m.source.SCOPE.rsplit('.', 1)[0] + '\n']:
            with self.assertRaises(ValueError): m.no_overlap(text)

    def test_alias_conflict_and_wrong_target(self):
        inst = copy.deepcopy(self.c['instances'][0])
        inst['bindings'][1]['allowed_labels'] = inst['bindings'][0]['allowed_labels']
        with self.assertRaises(ValueError): m.mature.singleton_aliases([inst])
        from xml.etree.ElementTree import Element
        target = next(b for b in inst['bindings'] if b['role'] == 'target')
        for key, value in [('portnode', '3'), ('left', '511'), ('right', '1'), ('type', '2')]:
            with self.assertRaises(ValueError):
                m.source.validate_node(Element(target['kind'], dict(target['attributes'], **{key: value})))

    def test_actual_tcl_session_eval_plain_global_config(self):
        with tempfile.TemporaryDirectory(dir=m.source.OUT) as td:
            out = Path(td); (out / 'DVEfiles').mkdir()
            c = dict(self.c, design='/frozen/design.vdb', sample='/admitted/sample.vdb',
                     test='/admitted/sample/test', python='/sealed/python', helper=str(Path(m.__file__).resolve()))
            (out / 'selection.tcl').write_text(m.mature.selection(c))
            (out / 'actual-selection.tcl').write_text(''.join('set ::re_targets(%d) [list %s]\n' %
                (k, '{bit_enable_mask[255:0]}' if k == 0 else '') for k in range(26)))
            (out / 'DVEfiles/dve_gui.log').write_text("The design '/frozen/design.vdb' was loaded successfully.\n")
            host = r'''
set ::re_test_only 1
set ::env(DVE_COVERAGE_OUTPUT) {%s}
eval [list source {%s}]
set ::events {}
proc dw_need {x message} {if {!$x} {error $message}}
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
            self.assertIn('before,apply,selected,resetcall,reset,load,reloaded,resetcall,final', result.stdout)


if __name__ == '__main__': unittest.main()
