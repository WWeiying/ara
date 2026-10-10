"""Actual compiled fixture, exact EL corruption, and host Tcl API selection tests."""
import copy
import json
import tkinter
import unittest

import qualify_dwc_points742 as q


def fixture_text(c):
    lines = []
    for scope, module, checksum, machine, machine_sha, mode, name, signature in c['fsm_records']:
        lines += ['CHECKSUM: "%s %s"' % (module, checksum), 'INSTANCE: ' + scope,
                  'Fsm %s "%s"' % (machine, machine_sha), '%s %s "%s"' % (mode, name, signature)]
    for t in c['toggles']:
        lines += ['CHECKSUM: "%s %s"' % (t['module'], t['checksum']), 'INSTANCE: ' + t['scope'],
                  'Toggle %s "logic %s"' % (t['signal'], t['label'])]
    return '\n'.join(lines) + '\n'


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = json.loads(q.REVIEW.read_bytes())
        cls.c = q.inventory(cls.review)
        cls.text = fixture_text(cls.c)

    def reject(self, text):
        self.assertNotEqual(text, self.text)
        with self.assertRaises(ValueError): q.parse_el(text, self.c)

    def test_actual_frozen_source_pins(self):
        self.assertEqual(q.life.digest(q.REVIEW), q.REVIEW_SHA)
        q.life.check(self.review['input_pins'])

    def test_complete_actual_shape(self):
        self.assertEqual(len(q.parse_el(self.text, self.c)), 63)
        self.assertEqual(sum(t['width'] * 2 for t in self.c['toggles']), 168)
        self.assertEqual(sum(len(g['rows']) for g in self.c['groups']), 39)

    def test_order_annotation_only(self):
        blocks = self.text.split('CHECKSUM: ')[1:]
        reordered = ''.join('CHECKSUM: ' + b for b in reversed(blocks))
        self.assertEqual(q.parse_el(self.text, self.c), q.parse_el(reordered + 'ANNOTATION: "audit"\n', self.c))

    def test_scope(self): self.reject(self.text.replace(q.proof.FILTER, q.proof.FILTER + '.other'))
    def test_checksum(self): self.reject(self.text.replace('2300800093', '2300800094'))
    def test_machine(self): self.reject(self.text.replace('w_state_q', 'other_state_q'))
    def test_state_native_id(self): self.reject(self.text.replace('State ABSORB_W "0"', 'State ABSORB_W "999"'))
    def test_duplicate(self): self.reject(self.text + self.text)
    def test_missing(self): self.reject('\n'.join(self.text.splitlines()[:-1]) + '\n')
    def test_width(self): self.reject(self.text.replace('w_cnt_d.cnt[1:0]', 'w_cnt_d.cnt[2:0]'))
    def test_interface(self): self.reject(self.text.replace('r_cnt_clear', 'slv_req_i.aw_valid'))
    def test_other_metric(self): self.reject(self.text + 'Line 42\n')

    def test_protected_normal_reset(self):
        scope, module, checksum, machine, machine_sha, _, _, _ = self.c['fsm_records'][0]
        self.reject(self.text + '\n'.join(['CHECKSUM: "%s %s"' % (module, checksum),
                    'INSTANCE: ' + scope, 'Fsm %s "%s"' % (machine, machine_sha),
                    'Transition W_FEEDTHROUGH->W_RESET "5->6"']) + '\n')

    def test_pin_drift(self):
        p = str(q.REVIEW)
        with self.assertRaises(ValueError): q.life.check({p: 'a' * 64})

    def test_host_tcl_selection(self):
        t = tkinter.Tcl()
        t.eval('set dw_test_only 1')
        t.call('source', str(q.TCL))
        t.eval('''
            set chosen {}; set bad 0
            proc gui_list_get_selected {args} {
                global chosen bad
                if {[lsearch -exact $args -flat] >= 0} {
                    if {$chosen eq ""} {return [list {}]}; return [list $chosen]
                }
                if {[lsearch -exact $args -count] >= 0} {return [expr {$chosen ne ""}]}
                if {$bad} {return wrongtoken}; return $chosen
            }
            proc gui_list_select {args} {
                global chosen
                if {[lsearch -exact $args -unselect] >= 0} {set chosen {}; return}
                set chosen [lindex [lindex $args end] 0]
            }
        ''')
        t.call('dw_select', 'native.path')
        self.assertEqual(str(t.eval('set chosen')), 'native.path')
        t.call('dw_select', 'next.path')
        t.setvar('bad', 1)
        with self.assertRaises(tkinter.TclError): t.call('dw_select', 'wrong.readback')

    def test_host_tcl_full_body_order(self):
        body = q.TCL.read_text()
        self.assertNotIn('lassign', body)
        t = tkinter.Tcl(); t.eval('set dw_test_only 1'); t.call('source', str(q.TCL))
        for proc in ('dw_session', 'dw_audit', 'dw_bind', 'dw_walk', 'dw_load', 'dw_reset'):
            self.assertTrue(t.call('info', 'complete', t.call('info', 'body', proc)))
        self.assertLess(body.index('dw_save first.el'), body.index('dw_load first.el'))
        self.assertIn('dw_audit final 0', body)
        self.assertIn('dw_save cleanup-empty.el 1', body)


if __name__ == '__main__': unittest.main()
