"""Batch native singleton guards; mocked/generated ELs are not product evidence."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import lzc_selector_native_product_batch as batch
from lzc_selector_native_prepare import tcl_word, write


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = json.loads((batch.product.OUT / 'lzc_selector_native_product_capture_prepare-707-20261006-01/capture-plan.json').read_bytes())
        cls.c = next(t['candidate'] for t in cls.plan['targets'] if t['candidate']['metric'] == 'cond')
        cls.branch = next(t['candidate'] for t in cls.plan['targets'] if t['candidate']['metric'] == 'branch')

    def tcl(self, body):
        script = 'set lpb_test_only 1\nsource ' + tcl_word(batch.SCRIPT) + '\n' + body
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_true_native_signature_and_wrong_scope_checksum_false_guards(self):
        c = self.c
        target = 'set target [list ' + ' '.join(map(tcl_word, (
            0, c['key'], c['scope'], 'cond', c['expression'], c['metric_checksum'], c['point_checksum'], 0))) + ']\n'
        with tempfile.TemporaryDirectory(dir=batch.product.OUT, prefix='lzc_selector_native_batch_unit-') as temp:
            root = Path(temp)
            template = (f'CHECKSUM: "{c["module_checksum"]} {c["metric_checksum"]}"\nINSTANCE: {c["scope"]}\n'
                        f'Condition 901 "{c["point_checksum"]}" "{c["expression"]} 1 -1" (907 "1")\n')
            samples = dict(valid=template, wrong_module=template.replace('3250293308', '438741478'),
                           wrong_scope=template.replace(c['scope'], 'other.child'),
                           wrong_point=template.replace(c['point_checksum'], '0'),
                           false=template.replace('(907 "1")', '(907 "0")'),
                           collateral=template + template)
            for name, text in samples.items():
                path = root / (name + '.el')
                write(path, text)
                failed = 0 if name == 'valid' else 1
                body = target + f'set failed [catch {{lpb_signature {tcl_word(path)} $target {{}}}} message]\n'
                body += f'if {{$failed != {failed}}} {{puts stderr "Guard failure: $message"; exit 1}}\nputs PASS\n'
                self.assertIn('PASS', self.tcl(body))

    def test_actual_standalone_signature_never_accepted_as_product(self):
        c = self.c
        path = batch.product.OUT / ('lzc_selector_native_successor-705-20261006-01/'
            'lzc_selector_native_w10_s0_p0/lzc_selector_native_capture-03/first-1.el')
        target = 'set target [list ' + ' '.join(map(tcl_word, (
            0, c['key'], c['scope'], 'branch', c['expression'], c['metric_checksum'], c['point_checksum'], 0))) + ']\n'
        body = target + f'if {{![catch {{lpb_signature {tcl_word(path)} $target 0}}]}} {{puts stderr "Root accepted"; exit 1}}\nputs PASS\n'
        self.assertIn('PASS', self.tcl(body))

    def test_native_parent_expression_match_not_xml_id(self):
        c = self.branch
        with tempfile.TemporaryDirectory(dir=batch.product.OUT, prefix='lzc_selector_native_batch_unit-') as temp:
            path = Path(temp) / 'parents.tcllist'
            body = 'set wanted ' + tcl_word(c['expression']) + '\n'
            body += r'''
proc gui_list_action {args} {}
proc gui_list_expand {args} {}
proc gui_list_get {args} {
    global wanted
    if {[lsearch -exact $args -text] >= 0} {
        set column [lindex $args [expr {[lsearch -exact $args -text] + 1}]]
        if {$column == 3} {return $wanted}; return other
    }
    set last [lindex $args end]
    if {[lsearch -exact $args -firstChild] >= 0} {
        if {$last eq "-firstChild"} {return P}
        if {$last eq "P"} {return A}; return {}
    }
    if {[lsearch -exact $args -path] >= 0} {return Item11}
    if {[lsearch -exact $args -meta] >= 0} {if {$last eq "A"} {return Branch11.0}; return Branch11.1}
    if {[lsearch -exact $args -nextSibling] >= 0} {if {$last eq "A"} {return B}; return {}}
    error "Unsupported query"
}
'''
            body += 'set target [list ' + ' '.join(map(tcl_word, (
                0, c['key'], c['scope'], 'branch', c['expression'], c['metric_checksum'], c['point_checksum'], -1))) + ']\n'
            body += f'set stream [open {tcl_word(path)} w]\nset identity [lpb_branch_binding $target $stream]\nclose $stream\n'
            body += 'if {$identity ne "11"} {puts stderr "Native text binding failed"; exit 1}\nputs PASS\n'
            self.assertIn('PASS', self.tcl(body))
            self.assertIn('binding', path.read_text())
            self.assertNotEqual(c['xml_provenance']['native_id'], '11')

    def test_audit_cannot_ignore_false_or_other_child_state(self):
        import csv
        rows = self.plan['protection_rows']
        with tempfile.TemporaryDirectory(dir=batch.product.OUT, prefix='lzc_selector_native_batch_unit-') as temp:
            path = Path(temp) / 'state.tsv'
            actual = [dict(position=str(i), scope=r['scope'], metric=r['metric'], native_id=r['native_id'] or '',
                           expression=r['expression'] or '', vector=r['vector'], excluded='0') for i, r in enumerate(rows)]
            fields = list(actual[0])
            with path.open('w') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t')
                writer.writeheader()
                writer.writerows(actual)
            self.assertEqual(batch.audit(path, rows, -1), 4200)
            actual[-1]['excluded'] = '1'
            with path.open('w') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t')
                writer.writeheader()
                writer.writerows(actual)
            with self.assertRaises(ValueError):
                batch.audit(path, rows, -1)

    def test_static_no_final_application_or_xml_id_selection(self):
        text = batch.SCRIPT.read_text()
        self.assertNotIn('xml_provenance', text)
        self.assertNotIn('apply_reviewed_waivers', text)
        self.assertIn('lpb_signature $first $target $identity', text)
        self.assertIn('gui_exclusion -reset', text)
        self.assertNotIn('aggregate.el', text)


if __name__ == '__main__':
    unittest.main()
