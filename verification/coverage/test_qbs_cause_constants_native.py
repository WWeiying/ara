import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import qbs_cause_constants_native as m


class ExactMembership(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, _, instances = m.proof()
        cls.c = dict(instances=instances, timeout_seconds=900, population_application=False,
                     automatic_retry=False, boundary=m.BOUNDARY)
        cls.text = m.candidate(cls.c)

    def test_full_source_partition(self):
        m.contract(self.c)
        self.assertEqual(len(m.records(self.text, self.c)), 1486)

    def test_whole_cause_and_protected_bit_rejected(self):
        for old, new in [('fault_mmu_exception_o.cause [4]', 'fault_mmu_exception_o.cause'),
                         ('fault_mmu_exception_o.cause [4]', 'fault_mmu_exception_o.cause [3]'),
                         ('fault_mmu_exception_o.cause [4]', 'fault_mmu_exception_o.cause [4:0]')]:
            with self.assertRaises(ValueError): m.records(self.text.replace(old, new), self.c)

    def test_unknown_object_type_scope_checksum_rejected(self):
        for old, new in [('logic fault_mmu_exception_o.cause[63:0]', 'logic fault_mmu_exception_o.cause[62:0]'),
                         ('logic fault_mmu_exception_o.cause', 'logic signed fault_mmu_exception_o.cause'),
                         ('fault_mmu_exception_o.cause [4]', 'fault_mmu_exception_o.tval [4]'),
                         ('INSTANCE: ' + self.c['instances'][0]['scope'], 'INSTANCE: other'),
                         ('CHECKSUM: "', 'CHECKSUM: "9')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                m.records(self.text.replace(old, new, 1), self.c)

    def test_missing_duplicate_or_mixed_direction_rejected(self):
        for changed in (self.text.replace('Toggle ', 'Toggle 0to1 ', 1),
                        self.text + self.text,
                        self.text.replace('Toggle ', 'Toggle 1to0 ', 1)):
            with self.assertRaises(ValueError): m.records(changed, self.c)

    def test_both_split_directions_and_reordered_members_equal(self):
        lines = []
        for line in self.text.splitlines():
            if line.startswith('Toggle '):
                lines += [line.replace('Toggle ', 'Toggle 0to1 ', 1),
                          line.replace('Toggle ', 'Toggle 1to0 ', 1)]
            else: lines.append(line)
        self.assertEqual(m.records('\n'.join(lines), self.c), m.records(self.text, self.c))

    def write_inventory(self, out, stage, index, alter=None):
        i = self.c['instances'][index]; target = {t['signal'] for t in i['targets']}
        rows = [['handle', 'path', 'meta', 'name', 'excluded']]
        for k, n in enumerate(i['nodes']):
            name = n['name'] + m.labels.bounds(n)
            flag = str(int(stage in ('selected', 'reloaded') and n['name'] in target))
            rows.append([str(k + 1000), name, name, name, flag])
        if alter: alter(rows)
        with (out / ('native_%s_%d.tsv' % (stage, index))).open('w', newline='') as f:
            csv.writer(f, delimiter='\t').writerows(rows)

    def test_full_inventory_five_stages_and_protected_flag_negative(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out = Path(tmp)
            for stage in m.STAGES:
                for index in range(3):
                    self.write_inventory(out, stage, index)
                    self.assertEqual(len(m.inventory(out, self.c, stage, index)), len(self.c['instances'][index]['nodes']))
            self.write_inventory(out, 'selected', 0, lambda rows: rows.__setitem__(1, rows[1][:-1] + ['1']))
            with self.assertRaises(ValueError): m.inventory(out, self.c, 'selected', 0)

    def test_inventory_missing_duplicate_array_dimensions_negative(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out = Path(tmp)
            for alter in (lambda rows: rows.pop(), lambda rows: rows.append(rows[1]),
                          lambda rows: rows[1].__setitem__(2, 'foreign-meta')):
                self.write_inventory(out, 'before', 0, alter)
                with self.assertRaises(ValueError): m.inventory(out, self.c, 'before', 0)
            # Root has two packed arrays; shape remains mandatory even though arrays are not targets.
            root_index = next(k for k, i in enumerate(self.c['instances']) if any(n['kind'] == 'arrays' for n in i['nodes']))
            def partial_array(rows):
                row = next(r for r in rows[1:] if 'ldu_result_id_o' in r[3])
                row[1] = row[2] = row[3] = 'ldu_result_id_o[3:0]'
            self.write_inventory(out, 'before', root_index, partial_array)
            with self.assertRaises(ValueError): m.inventory(out, self.c, 'before', root_index)

    def test_global_empty_and_retained_member_complements(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out = Path(tmp)
            for stage, name in m.EL_FILES.items():
                (out / name).write_text(self.text if stage in ('selected', 'reloaded') else '')
                self.assertEqual(len(m.el(out, self.c, stage)), 1486 if stage in ('selected', 'reloaded') else 0)
            (out / 'final-empty.el').write_text('\n')
            with self.assertRaises(ValueError): m.el(out, self.c, 'final')

    def test_actual_selection_and_eval_session_all_host_gates(self):
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out = Path(tmp)
            c = dict(self.c, design='design', sample='sample', test='test', python=sys.executable,
                     helper=str(m.HERE / 'qbs_cause_constants_native.py'), output=str(out), pins={})
            (out / 'selection.tcl').write_text(m.selection(c))
            (out / 'candidate.el').write_text(self.text)
            c['pins'] = {str(out / name): m.life.digest(out / name) for name in ('selection.tcl', 'candidate.el')}
            m.life.save(out / 'config.json', c)
            seal = m.life.digest(out / 'config.json')
            script = 'set ::qc_test_only 1\n'
            # Read the actual entry, then evaluate it: info script is empty, as in DVE -script.
            script += 'set stream [open {' + str(m.ENTRY) + '} r]\nset body [read $stream]\nclose $stream\neval $body\n'
            script += 'set ::env(DVE_COVERAGE_OUTPUT) {' + tmp + '}\nset ::env(QBS_CAUSE_CONSTANTS_SEAL) {' + seal + '}\n'
            script += 'set ::active 0\nset ::root ara_tb\narray set ::selected {CovDetail.1 {} CoverageTable.1 {}}\n'
            for i in c['instances']:
                labels = [n['name'] + m.labels.bounds(n) for n in i['nodes']]
                targets = [n['name'] + m.labels.bounds(n) for n in i['nodes'] if n['name'] in {t['signal'] for t in i['targets']}]
                script += 'set ::model(' + i['scope'] + ') [list ' + ' '.join(m.atom(v) for v in labels) + ']\n'
                script += 'set ::targets(' + i['scope'] + ') [list ' + ' '.join(m.atom(v) for v in targets) + ']\n'
            script += r'''
proc gui_open_cov {args} {
    if {$::qc_design ne "design" || $::qc_sample ne "sample" || $::qc_test ne "test"} {error "Actual selection did not source"}
}
proc gui_covtable_show {args} {}
proc gui_covtable_setroot {args} {set ::root [lindex $args end]}
proc gui_cov_show_value {args} {}
proc gui_process_events {args} {}
proc gui_list_expand {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_cov_tgl_double_click {args} {error "Forbidden per-bit GUI authority"}
proc gui_list_get_selected {args} {
    set id [lindex $args 1]
    if {[lsearch $args -count]>=0} {return [llength $::selected($id)]}
    return [list $::selected($id)]
}
proc gui_list_select {args} {
    set id [lindex $args 1]
    if {[lsearch $args -unselect]>=0} {set ::selected($id) {};return}
    set ::selected($id) [lindex $args end]
}
proc gui_list_get_property {args} {
    set k [expr {[lindex $args end]-5}]
    if {$k>=6} {error "No column"}
    return [lindex {Score Line Toggle FSM Condition Branch} $k]
}
proc gui_list_get {args} {
    set id [lindex $args 1];set flag [lindex $args 2]
    if {$id eq "CoverageTable.1"} {
        if {$flag eq "-firstChild"} {return 1}
        if {$flag eq "-nextSibling"} {return 0}
        if {$flag eq "-text" && [lindex $args 3]>=5} {
            if {[lindex $args 3]==7} {return [expr {$::active?51.0:50.0}]}
            return 60.0
        }
        return [lindex [split $::root .] end]
    }
    set objects $::model($::csr_scope)
    if {$flag eq "-firstChild"} {if {[llength $args]==3} {return 1000};return 0}
    if {$flag eq "-nextSibling"} {
        set next [expr {[lindex $args end]+1}]
        if {$next-1000<[llength $objects]} {return $next};return 0
    }
    return [lindex $objects [expr {[lindex $args end]-1000}]]
}
proc gui_exclusion {args} {
    if {[lsearch $args -reset]>=0} {set ::active 0;return}
    if {[lsearch $args -recalculate]>=0} {return}
    if {[lsearch $args -tgl_transition]>=0} {error "Forbidden per-bit GUI flag"}
    set name [lindex $::selected(CovDetail.1) 0]
    return [expr {$::active && [lsearch -exact $::targets($::csr_scope) $name]>=0}]
}
proc gui_exclusion_file {args} {
    set file [lindex [lindex $args end] 0]
    if {[lsearch $args -load]>=0} {
        if {![file exists $file]} {error "Load absent"}
        set f [open $file r];set ::saved [read $f];close $f;set ::active 1;return
    }
    set f [open $file w];if {$::active} {puts -nonewline $f $::saved};close $f
}
qc_session
if {$::active} {error "Final reset missing"}
puts FULL_ACTUAL_ENTRY_HOST_PASS
'''
            result = subprocess.run(['tclsh'], input='if {[catch {\n' + script + '\n} msg]} {puts stderr $msg;puts stderr $::errorInfo;exit 1}\n',
                                    cwd=m.life.ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('FULL_ACTUAL_ENTRY_HOST_PASS', result.stdout)
            actual = json.loads((out / 'actual-binding.json').read_text())
            self.assertEqual(actual['actual_objects'], 622)
            for stage in m.STAGES:
                for index in range(3): m.inventory(out, c, stage, index)
                m.el(out, c, stage); m.metrics(out, c, stage)
            self.assertEqual(m.el(out, c, 'selected'), m.el(out, c, 'reloaded'))
            self.assertEqual((out / 'cleanup-empty.el').read_bytes(), b'')


if __name__ == '__main__': unittest.main()
