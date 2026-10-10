import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import qbs_bank1_group_hit_native791_v2 as c


def identity_text(path):
    reader = csv.reader(io.StringIO(path.read_text()), delimiter='\t')
    rows = list(reader)
    stream = io.StringIO(); writer = csv.writer(stream, delimiter='\t', lineterminator='\n')
    writer.writerows([r[:4] for r in rows])
    return stream.getvalue()


class IdentityEL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = c.life.read_bound(c.FAILED/'config.json', c.FAILED_SEAL)
        cls.first = (c.FAILED/'first.el').read_text()

    def test_actual_four_full_stages_all6707_native_identities(self):
        for k, instance in enumerate(self.config['instances']):
            before = c.bound_rows(identity_text(c.FAILED/('native_before_%d.tsv'%k)), instance, 'before')
            for stage in ('selected','reset','reloaded'):
                actual = identity_text(c.FAILED/('native_%s_%d.tsv'%(stage,k)))
                self.assertEqual(c.bound_rows(actual, instance, stage), before)
        self.assertEqual(sum(len(i['bindings']) for i in self.config['instances']), 6707)

    def test_actual_final_partial_reject_and_failed_status(self):
        evidence = c.failure_evidence()
        self.assertEqual(evidence['status'], 'FAILED_NOT_APPLIED')
        i = self.config['instances'][1]
        with self.assertRaises(ValueError):
            c.bound_rows(identity_text(c.FAILED/'native_final_1.tsv'), i, 'final')

    def test_actual_saved_EL_both_semantic_order_independent(self):
        second = (c.FAILED/'second.el').read_text()
        self.assertEqual(c.records(self.first, self.config), c.records(second, self.config))
        self.assertEqual(len(c.records(self.first, self.config)), 3232)

    def test_native_identity_negatives_and_no_flags_schema(self):
        i = self.config['instances'][0]
        text = identity_text(c.FAILED/'native_before_0.tsv'); lines = text.splitlines()
        for bad in ('\n'.join(lines[:-1])+'\n', text.replace(lines[1], lines[2], 1),
                    text.replace(lines[1].split('\t')[3], 'foreign[31:0]', 1),
                    (c.FAILED/'native_before_0.tsv').read_text()):
            with self.assertRaises(ValueError): c.bound_rows(bad, i, 'before')

    def test_actual_EL_foreign_scope_metric_checksum_range_duplicates(self):
        target = c.target_config(self.config)['instances'][0]['signals'][0]
        protected = next(b for b in range(32) if b not in target['bits'])
        line = 'Toggle 0to1 '+target['name']+' ['+str(protected)+']'
        for bad in (self.first+'\n'+line, self.first.replace('Toggle', 'Branch', 1),
                    self.first.replace(self.config['plan']['scope'], self.config['plan']['scope']+'.foreign', 1),
                    self.first.replace('3028946256', '0', 1),
                    self.first+'\nToggle '+target['name'], self.first+'\n'+next(x for x in self.first.splitlines() if x.startswith('Toggle'))):
            with self.assertRaises(ValueError): c.records(bad, self.config)

    def test_whole_child_protected_and_empty_reset_final(self):
        for stage in ('before','reset','final'):
            self.assertEqual(c.check_el(c.FAILED, self.config, stage), 0)
        child = self.config['instances'][1]
        text = 'CHECKSUM: "%s %s"\nINSTANCE: %s\nToggle data\n' % (
            child['design_module_checksum'], child['toggle_checksum'], child['scope'])
        with self.assertRaises(ValueError): c.records(self.first+text, self.config)
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as tmp:
            out = Path(tmp); (out/'final-empty.el').write_text(self.first)
            with self.assertRaises(ValueError): c.check_el(out, self.config, 'final')

    def test_actual_session_eval_all130_identity_snapshots_no_row_select(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as tmp:
            out = Path(tmp)
            (out/'selection.tcl').write_text((c.FAILED/'selection.tcl').read_text())
            (out/'live-ready').write_text('HOST_MOCK_ONLY\n')
            script = '''set ::bg_v2_test_only 1
set ::env(DVE_COVERAGE_OUTPUT) {%s}
proc bootstrap {} {uplevel #0 [list source {%s}]}
bootstrap
set ::calls {}
proc bg_call {args} {lappend ::calls $args; return MOCK}
proc p740_root {} {}
proc gui_open_cov {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc dw_save {args} {}
proc dw_load {args} {}
proc dw_reset {} {}
proc dw_select {args} {error "ROW SELECTION FORBIDDEN"}
proc gui_exclusion {args} {error "ROW FLAG QUERY FORBIDDEN"}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0 && [llength $args] == 3} {return 1}
    if {[lsearch -exact $args -path] >= 0 || [lsearch -exact $args -meta] >= 0 || [lsearch -exact $args -text] >= 0} {return native_mock_object}
    return 0
}
eval {bg_session}
foreach stage {before selected reset reloaded final} {
    set count 0
    foreach call $::calls {if {[lindex $call 0] eq "inventory" && [lindex $call 2] eq $stage} {incr count}}
    if {$count != 26} {error "missing fullstage $stage"}
}
puts HOST_ACTUAL_SESSION_130_SNAPSHOT_NO_SELECTION_PASS
''' % (out, c.ENTRY)
            result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr); self.assertEqual(result.stderr, '')
            self.assertIn('HOST_ACTUAL_SESSION_130_SNAPSHOT_NO_SELECTION_PASS', result.stdout)
            for stage in c.STAGES:
                for k in range(26):
                    lines = (out/('native_%s_%d.tsv'%(stage,k))).read_text().splitlines()
                    self.assertEqual(lines[0], 'handle\tpath\tmeta\tname')
                    self.assertEqual(len(lines), 2)

    def test_private_namespace_keeps_v1_frozen(self):
        self.assertEqual(c.life.digest(Path(c.frozen.__file__)), c.V1_SHA)
        self.assertIsNot(c.inventory.__globals__, vars(c.frozen))
        self.assertIs(c.inventory.__globals__['bound_rows'], c.bound_rows)
        self.assertIs(c.run.__globals__['inspect'], c.inspect)

    def test_fresh_before_alias_drift_rejected(self):
        config = dict(self.config)
        index = next(k for k, i in enumerate(config['instances'])
                     if any(len(b['allowed_labels']) > 1 for b in i['bindings']))
        i = config['instances'][index]
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as tmp:
            out = Path(tmp); c.life.save(out/'config.json', config)
            before = out/('native_before_%d.tsv'%index)
            before.write_text(identity_text(c.FAILED/('native_before_%d.tsv'%index)))
            found = c.bound_rows(before.read_text(), i, 'before')
            c.life.save(out/'actual-binding.json', dict(config_sha256=c.life.digest(out/'config.json'),
                before_pins={str(before):c.life.digest(before)}, scopes=[found]*(index+1)))
            selected = out/('native_selected_%d.tsv'%index); selected.write_text(before.read_text())
            self.assertEqual(c.inventory(out, config, 'selected', index), found)
            binding = next(b for b in i['bindings'] if len(b['allowed_labels']) > 1)
            name = binding['attributes']['name']; old = found[name]['label']
            other = next(a for a in binding['allowed_labels'] if a != old)
            selected.write_text(selected.read_text().replace(old, other))
            with self.assertRaisesRegex(ValueError, 'Fresh before identity drift'):
                c.inventory(out, config, 'selected', index)

    def test_terminal_false_bool_timeout_incomplete_rejected(self):
        with tempfile.TemporaryDirectory(dir=c.life.OUT) as tmp:
            out = Path(tmp)
            for terminal in (dict(returncode=False, timeout=False, actual_dve=[{}]),
                             dict(returncode=0, timeout=True, actual_dve=[{}]),
                             dict(returncode=0, timeout=False, actual_dve=[])):
                (out/'terminal.json').write_text(json.dumps(terminal))
                with patch.object(c, 'check', return_value=self.config):
                    with self.assertRaisesRegex(ValueError, 'Strict actual terminal'):
                        c.inspect(out, 'HOST_MOCK_ONLY')


if __name__ == '__main__': unittest.main()
