"""Actual source/shape plus Tcl8.4-style GUI model; never native approval."""
import copy
import csv
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import alua_group5_native137 as n


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = json.loads(n.PACKET.read_bytes())
        cls.bitmap = json.loads((n.source.BASE.parent/'combined-bits.json').read_bytes())
        config = json.loads((n.source.OUT/'current-population794-soc61-parent-20261008-01/config.json').read_bytes())
        cls.design = n.source.Design(Path(config['input_ledger'][0]))
        cls.scopes = n.build_plan(cls.packet,cls.bitmap,cls.design)
        cls.config = dict(schema=n.SCHEMA,source_packet_seal=n.PACKET_SHA,targets={'branch':137},
            protected={'branch':267},annotation=n.ANNOTATION,timeout_seconds=1800,
            application_approval=False,automatic_retry=False,initial_X_qualified=False,
            plan=dict(scopes=cls.scopes,design_vdb=config['input_ledger'][0],
                      selected_test_vdb=config['input_ledger'][-1]))

    def raw(self):
        lines = []
        for scope,metrics in self.scopes.items():
            first = metrics['branch'][0]
            lines.extend(['CHECKSUM: "%s %s"' % (first['module_checksum'],first['metric_checksum']),
                          'INSTANCE: '+scope])
            for row in metrics['branch']:
                if not row['target']:continue
                p = row['point']
                lines.extend(['ANNOTATION: "'+n.ANNOTATION+'"',
                    'Branch 5 "%s" "cmd.conv" (%s) "%s"' %
                    (p['attributes']['chksum'],p['vector'],n.primitive.quoted(row['expected_signature']))])
        return ('\n'.join(lines)+'\n').encode('ascii')

    def test_actual_frozen_source_complete_replay(self):
        self.assertEqual(n.sha(n.PACKET),n.PACKET_SHA)
        self.assertEqual(n.source.collect(),self.packet)

    def test_exact137_47_and_all_other_groups(self):
        n.validate(self.config)
        self.assertEqual(sum(len(m['branch']) for m in self.scopes.values()),404)
        self.assertEqual(sum(not r['target'] for m in self.scopes.values() for r in m['branch']),267)
        self.assertTrue(all(r['module_checksum']=='1532764271' and r['metric_checksum']=='1417162425'
                            for m in self.scopes.values() for r in m['branch']))
        raw = n.bind_native(self.raw(),self.config)
        self.assertEqual(len(raw),137)

    def test_real_saved_prior_group5_signatures_match_compiled_formula(self):
        path = n.source.OUT/'operand-parameter720-native-reuse-772-agent-20261007-01/candidate720.el'
        group = next(g for g in self.design.definition(next(iter(self.scopes)),'branch').iter('branch_spec') if g.get('id')=='5')
        points = {r['point']['vector']:r['point'] for r in next(iter(self.scopes.values()))['branch'] if r['point']['native_id']=='5'}
        measured = 0
        for line in path.read_text().splitlines():
            match = re.fullmatch(r'Branch 5 "718333796" "cmd.conv" \((\d+)\) "(.*)"',line)
            if match:
                self.assertEqual(match[2],n.primitive.quoted(n.signature(group,points[match[1]])))
                measured += 1
        self.assertGreater(measured,0)

    def test_native_wrong_scope_module_group_signature_and_othermetrics_rejected(self):
        raw = self.raw()
        mutations = [raw.replace(b'1532764271',b'1417162425',1),
                     raw.replace(b'718333796',b'718333795',1),
                     raw.replace(b'i_operand_queue_alu_a',b'i_operand_queue_mask_b',1),
                     raw.replace(b'"cmd.conv"',b'"cmd.eew"',1),
                     raw.replace(b'cmd.conv default',b'cmd.conv FOREIGN',1),
                     raw+b'Toggle x "logic x"\n',raw+b'Condition 1 "x"\n',
                     raw+b'CHECKSUM: "1 2"\nINSTANCE: whole_scope\n']
        for value in mutations:
            with self.subTest(value=value[-100:]),self.assertRaises(Exception):n.bind_native(value,self.config)

    def test_source_target_hit_unknown_and_protected_target_rejected(self):
        scope = next(iter(self.scopes));target = next(r for r in self.scopes[scope]['branch'] if r['target'])
        bitmap = copy.deepcopy(self.bitmap);row = bitmap['metrics']['branch'][scope]
        row['bits'] = hex(int(row['bits'],16)|(1 << (row['width']-1-target['point']['raw_index'])))
        with self.assertRaises(Exception):n.build_plan(self.packet,bitmap,self.design)
        packet = copy.deepcopy(self.packet);packet['protected_group5_vectors'].pop()
        with self.assertRaises(Exception):n.build_plan(packet,self.bitmap,self.design)

    def write_states(self,path,stage,bad=False,missing=False,identity=False):
        with path.open('w',newline='') as f:
            writer = csv.writer(f,delimiter='\t');writer.writerow(['scope','metric','coordinate','meta','path','excluded'])
            count = 0
            for scope,m in self.scopes.items():
                for row in m['branch']:
                    count += 1
                    if missing and count==404:continue
                    sid,vid = row['coordinate'].split(',');meta = 'Branch'+sid+'.'+vid
                    state = int(stage in ('selected','reloaded') and row['target'])
                    if bad and not row['target']:state = 1
                    writer.writerow([scope,'branch',row['coordinate'],meta,
                                     'WRONG' if identity else 'Item'+sid+'.'+meta,state])

    def test_full404_five_stage_protection_and_identity_negatives(self):
        with tempfile.TemporaryDirectory(dir=n.source.OUT) as directory:
            path = Path(directory)/'states.tsv';identities = None
            for stage in n.STAGES:
                self.write_states(path,stage);identities = n.audit_states(path,self.config,stage,identities)
            self.assertEqual(len(identities),404)
            for kwargs in ({'bad':True},{'missing':True},{'identity':True}):
                self.write_states(path,'selected',**kwargs)
                with self.assertRaises(Exception):n.audit_states(path,self.config,'selected')

    def test_without_parent_review_no_launch(self):
        with patch.object(n.primitive,'private') as launcher:
            with self.assertRaises(Exception):n.run(Path('/unused'),'a'*64,None)
            launcher.assert_not_called()

    def test_actual_generated_Tcl_full_entry_five_stage(self):
        with tempfile.TemporaryDirectory(dir=n.source.OUT) as directory:
            out = Path(directory);(out/'branch-library.tcl').write_text(n.primitive.branch_library())
            selection = n.debug.selection(self.config['plan'])+'set a137_annotation {'+n.ANNOTATION+'}\nset a137_pythonpath {/absolute/host-stub-only}\n'
            (out/'selection.tcl').write_text(selection);(out/'live-ready').write_text('HOST_ONLY')
            sample = Path(self.config['plan']['selected_test_vdb'])
            script = r'''
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(A137_CAPTURE_SEAL) HOST_ONLY
array set exclusions {};set selected {}
proc gui_list_action {args} {set ::scope [lindex $args end]}
proc gui_covdetail_query {args} {return Branch}
proc gui_list_expand {args} {}
proc children {item} {
    set result {}
    if {$item eq "ROOT"} {
        foreach key $::dbg_keys($::scope|branch) {
            set id [lindex [split $key ,] 0];set parent Item$id
            if {[lsearch -exact $result $parent]<0} {lappend result $parent}
        }
    } else {
        regexp {^Item([0-9]+)$} $item unused id
        foreach key $::dbg_keys($::scope|branch) {
            set parts [split $key ,]
            if {[lindex $parts 0] eq $id} {lappend result Item$id.Branch$id.[lindex $parts 1]}
        }
    }
    return $result
}
proc gui_list_get {args} {
    set op [lindex $args 2];set item [lindex $args 3]
    if {$op eq "-firstChild"} {if {$item eq ""} {set item ROOT};return [lindex [children $item] 0]}
    if {$op eq "-nextSibling"} {
        set parent ROOT
        if {[regexp {^(Item[0-9]+)\.} $item unused p]} {set parent $p}
        set list [children $parent];return [lindex $list [expr {[lsearch -exact $list $item]+1}]]
    }
    if {$op eq "-path"} {return $item}
    if {$op eq "-meta"} {return [join [lrange [split $item .] 1 end] .]}
    if {$op eq "-childCount"} {return 0}
    error "Unknown GUI stub operation $op"
}
proc gui_list_get_selected {args} {return $::selected}
proc gui_list_select {args} {
    if {[lsearch -exact $args -unselect]>=0} {set ::selected {};return}
    set ::selected [lindex $args [expr {[lsearch -exact $args -select]+1}]]
}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset]>=0} {array unset ::exclusions;array set ::exclusions {};return}
    if {[lsearch -exact $args -recalculate]>=0} {return}
    return [expr {[info exists ::exclusions($::scope|$::selected)]}]
}
proc gui_exclude_items {args} {
    if {[lsearch -exact $args -list]<0 || [lindex $args [expr {[lsearch -exact $args -list]+1}]] ne "branch"} {error "Wrong metric"}
    set ::exclusions($::scope|$::selected) 1
}
proc gui_cov_excl_review {args} {return 1}
proc gui_open_cov {args} {}
proc gui_exit {args} {set ::exited 1}
proc gui_exclusion_file {args} {
    set path [lindex $args [expr {[lsearch -exact $args -file]+1}]]
    if {[lsearch -exact $args -save]>=0} {
        set f [open $path w];if {[array size ::exclusions]} {puts $f [array get ::exclusions]};close $f
    } else {
        set f [open $path r];set values [read $f];close $f
        array unset ::exclusions;array set ::exclusions $values
    }
}
proc exec {args} {return ALUA137_HOST_STUB_ONLY}
source {%s}
if {![info exists ::exited] || [array size ::exclusions]!=0} {error "No actual final reset/exit in model"}
''' % (out,n.TCL)
            result = subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('ALUA137_FIVE_STAGE_DONE',result.stdout,result.stdout+result.stderr)
            previous = None
            for stage in n.STAGES:previous = n.audit_states(out/('states_'+stage+'.tsv'),self.config,stage,previous)
            for name in ('initial-empty.el','reset-empty.el','final-empty.el'):self.assertEqual((out/name).read_bytes(),b'')
            interp = tkinter.Tcl()
            records = []
            for name in ('first.el','second.el'):
                values = interp.splitlist((out/name).read_text())
                records.append(dict(zip(values[::2],values[1::2])))
            self.assertEqual(records[0],records[1])
            self.assertEqual(len(records[0]),137)


if __name__ == '__main__':unittest.main()
