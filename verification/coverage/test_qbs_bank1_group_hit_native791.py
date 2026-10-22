import copy
import csv
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

import qbs_bank1_group_hit_native791 as c


class ExactLocal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = c.plan.collect()
        cls.config = dict(plan=cls.p, instances=c.instances(cls.p))
        cls.target = c.target_config(cls.config)
        cls.el = c.partial.primitive.candidate(cls.target)

    def rows(self, i, stage='before'):
        f = io.StringIO(); w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['handle', 'path', 'meta', 'name', 'excluded'])
        for k, b in enumerate(i['bindings']):
            label = b['allowed_labels'][0]
            flag = int(b['role'] == 'target' and stage in ('selected', 'reloaded'))
            w.writerow([k+1, label, label, label, flag])
        return f.getvalue()

    def test_all26_complete_compiled_binding(self):
        self.assertEqual(len(self.config['instances']), 26)
        for i in self.config['instances']:
            for stage in c.STAGES:
                self.assertEqual(len(c.bound_rows(self.rows(i, stage), i, stage)), len(i['bindings']))

    def test_exact_partial_EL_and_permutation(self):
        result = c.records(self.el, self.config)
        self.assertEqual(len(result), 3232)
        lines = self.el.splitlines()
        self.assertEqual(result, c.records('\n'.join(lines[:3]+list(reversed(lines[3:]))), self.config))

    def test_measured_partial_EL_provenance(self):
        old = c.life.read_bound(c.TEMPLATE/'config.json', c.TEMPLATE_SHA)
        for name in ('first.el', 'second.el'):
            self.assertEqual(len(c.partial.parse_el((c.TEMPLATE/name).read_text(), old)), 19328)

    def test_EL_negative_foreign_missing_duplicate_checksum_whole(self):
        lines = self.el.splitlines(); name = self.target['instances'][0]['signals'][0]['name']
        for text in (self.el+'\n'+lines[3], '\n'.join(lines[:-1]),
                     self.el.replace('Toggle 0to1', 'Branch', 1),
                     self.el.replace(name, 'foreign', 1),
                     self.el.replace(lines[0], 'CHECKSUM: "0 3028946256"', 1),
                     self.el+'\nToggle '+name):
            with self.subTest(text=text[-100:]), self.assertRaises(ValueError): c.records(text, self.config)

    def test_protected704_retained_vector_bits_rejected(self):
        signal = self.target['instances'][0]['signals'][0]
        bit = next(b for b in range(32) if b not in signal['bits'])
        with self.assertRaises(ValueError):
            c.records(self.el+'Toggle 0to1 '+signal['name']+' ['+str(bit)+']\n', self.config)

    def test_foreign_native_type_range_and_missing_array(self):
        for i in self.config['instances']:
            original = self.rows(i)
            rows = original.splitlines()
            for text in ('\n'.join(rows[:-1])+'\n', original.replace(rows[1], rows[2], 1),
                         original.replace(rows[1].split('\t')[3], 'foreign[31:0]', 1)):
                with self.assertRaises(ValueError): c.bound_rows(text, i, 'before')

    def test_child_output_port_and_array_protection(self):
        for i in self.config['instances']:
            if i['scope'] == self.p['scope']: continue
            rows = self.rows(i).splitlines()
            cols = rows[1].split('\t'); cols[-1] = '1'; rows[1] = '\t'.join(cols)
            with self.assertRaises(ValueError): c.bound_rows('\n'.join(rows)+'\n', i, 'selected')

    def test_plain_Tcl_eval_actual_session_allfive_scopes(self):
        # Exercise the actual entry and generated configuration in proc/eval
        # context. GUI data are mocked; this is NOT native evidence.
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as temp:
            out = Path(temp)
            selection = ''.join('set ::bg_'+k+' {'+v+'}\n' for k, v in
                dict(design='design', sample='sample', test='test', python='python', helper='helper').items())
            selection += 'set ::bg_scopes [list '+' '.join('{'+i['scope']+'}' for i in self.config['instances'])+']\n'
            (out/'selection.tcl').write_text(selection)
            (out/'live-ready').write_text('MOCK_NOT_NATIVE\n')
            fixture = '''set ::bg_test_only 1
set ::env(DVE_COVERAGE_OUTPUT) {%s}
proc bootstrap {} {uplevel #0 [list source {%s}]}
bootstrap
set ::calls {}
proc bg_call {args} {lappend ::calls $args; return MOCK}
proc gui_open_cov {args} {}
proc gui_list_action {args} {set ::scope [lindex $args end]}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_get {args} {return 0}
proc p740_root {} {}
proc dw_save {args} {}
proc dw_load {args} {}
proc dw_reset {} {}
eval {bg_session}
puts "CALLS [llength $::calls]"
foreach s {before selected reset reloaded final} {
    set count 0
    foreach call $::calls {if {[lindex $call 0] eq "inventory" && [lindex $call 2] eq $s} {incr count}}
    if {$count != 26} {error "missing $s snapshots"}
}
puts MOCK_ACTUAL_SESSION_FIVE_STAGE_PASS
''' % (out, c.ENTRY)
            result = subprocess.run(['tclsh'], input=fixture, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            self.assertIn('CALLS 137', result.stdout)
            self.assertIn('MOCK_ACTUAL_SESSION_FIVE_STAGE_PASS', result.stdout)

    def test_owner_starttime_cgroup_uid_ancestor_negatives(self):
        worker = dict(pid=10, starttime=20, uid=1000, cgroup='0::/user.slice/test.service', invocation_id='sealed')
        actual = dict(pid=30, starttime=25, uid=1000, cgroup=worker['cgroup'], ancestors=[15, 10])
        c.owning_identity(actual, worker, 15)
        for key, value in [('pid', False), ('starttime', 19), ('uid', 0),
                           ('cgroup', '0::/foreign.service'), ('ancestors', [15])]:
            bad = dict(actual, **{key:value})
            with self.assertRaises(ValueError): c.owning_identity(bad, worker, 15)


if __name__ == '__main__': unittest.main()
