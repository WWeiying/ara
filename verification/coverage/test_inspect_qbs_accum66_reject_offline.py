import csv
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import inspect_qbs_accum66_reject_offline as m


class RejectEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = m.original.life.read_bound(m.OUT / 'config.json', m.SEAL)

    def test_actual_full_readonly_inspection(self):
        result = m.collect()
        self.assertFalse(result['native_qualified'])
        self.assertFalse(result['coverage_admitted'])
        self.assertEqual(result['before_objects'], 2425)
        self.assertEqual(len(result['missing_required_stages']), 4)
        self.assertEqual(json.loads(json.dumps(result)), result)

    def altered(self, change):
        with tempfile.TemporaryDirectory(dir=m.original.life.OUT) as temp:
            out = Path(temp) / 'copy'
            shutil.copytree(m.OUT, out)
            change(out)
            with self.assertRaises(ValueError): m.validate(out, self.config)

    def test_terminal_timeout_nonzero_missing_native_rejected(self):
        for key, value in [('timeout', True), ('returncode', 1), ('actual_dve', [])]:
            def alter(out, key=key, value=value):
                p = out / 'terminal.json'; d = json.loads(p.read_text()); d[key] = value
                p.write_text(json.dumps(d))
            self.altered(alter)

    def test_protected_exclusion_missing_identity_and_partial_shape_rejected(self):
        for mode in ('excluded', 'missing', 'meta', 'array'):
            def alter(out, mode=mode):
                index = next(i for i, v in enumerate(self.config['instances'])
                             if mode != 'array' or any(n['kind'] == 'arrays' for n in v['nodes']))
                p = out / ('native_before_%d.tsv' % index)
                with p.open(newline='') as stream:
                    rows = list(csv.reader(stream, delimiter='\t'))
                if mode == 'missing': rows.pop()
                elif mode == 'excluded': rows[1][-1] = '1'
                elif mode == 'meta': rows[1][2] = 'wrong-meta'
                else:
                    name = next(n['name'] for n in self.config['instances'][index]['nodes'] if n['kind'] == 'arrays')
                    row = next(r for r in rows[1:] if r[3].startswith(name + '['))
                    row[1] = row[2] = row[3] = name + '[0]'
                with p.open('w', newline='') as stream: csv.writer(stream, delimiter='\t').writerows(rows)
            self.altered(alter)

    def test_later_stage_forgery_or_nonempty_reset_rejected(self):
        self.altered(lambda out: (out / 'first.el').write_text((out / 'candidate.el').read_text()))
        self.altered(lambda out: (out / 'cleanup-empty.el').write_text('\n'))
        self.altered(lambda out: (out / 'native_selected_0.tsv').write_text('fabricated'))

    def test_candidate_missing_direction_or_wrong_checksum_rejected(self):
        for old, new in [('Toggle ', 'Toggle 0to1 '), ('CHECKSUM: "', 'CHECKSUM: "9')]:
            def alter(out, old=old, new=new):
                p = out / 'candidate.el'; p.write_text(p.read_text().replace(old, new, 1))
            self.altered(alter)

    def test_actual_table_proc_rejects_compound_display_with_exact_fullscope_token(self):
        scope = self.config['instances'][3]['scope']
        script = 'source ' + m.original.atom(m.original.HERE / 'apply_points740_v4.tcl') + '\n'
        script += 'set target ' + m.original.atom(scope) + '\n'
        script += 'set ' + m.original.atom('::p740_root_names(' + scope + ')') + ' {i_opgroup_block}\n'
        script += r'''
set root ara_tb
set selected {}
proc gui_covtable_show {args} {}
proc gui_cov_show_value {args} {}
proc gui_process_events {args} {}
proc gui_list_expand {args} {}
proc gui_covtable_setroot {args} {set ::root [lindex $args end]}
proc gui_list_get_selected {args} {return [list $::selected]}
proc gui_list_select {args} {
    if {[lsearch $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args end]
}
proc gui_list_get {args} {
    set flag [lindex $args 2]
    if {$flag eq "-firstChild"} {return 1}
    if {$flag eq "-nextSibling"} {return 0}
    if {$::root eq "ara_tb"} {return ara_tb}
    return {gen_operation_groups[0].i_opgroup_block}
}
set stream [open /dev/null w]
set failed [catch {p740_row $target $stream before} msg]
close $stream
if {!$failed || $msg ne "Nonunique root not bound to exact fullscope/displayed node"} {error "Wrong guard failure"}
if {[lindex $selected 0] ne $target || $root ne $target} {error "Fullscope token changed"}
puts EXACT_TOKEN_COMPOUND_DISPLAY_GUARD_REPRODUCED
'''
        r = subprocess.run(['tclsh'], input='if {[catch {\n' + script + '\n} msg]} {puts stderr $msg;puts stderr $::errorInfo;exit 1}\n',
                           cwd=m.original.life.ROOT, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('EXACT_TOKEN_COMPOUND_DISPLAY_GUARD_REPRODUCED', r.stdout)


if __name__ == '__main__': unittest.main()
