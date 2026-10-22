import copy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_rvh_branch_pilot_725 as subject


class PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        plan=json.loads((subject.PLAN_ROOT/'native-plan.json').read_bytes())
        cls.config=dict(schema='RVH725_EXACT3_NATIVE_PILOT_V1',source_plan_seal=subject.PLAN_SHA,
            plan=dict(scopes=plan['pilot_scopes'],selected_test_vdb=str(subject.SAMPLE),
                      design_vdb=plan['design_vdb']),targets={'branch':3},protected={'branch':97},
            annotation=subject.ANNOTATION,launch_approved=False,automatic_retry=False,
            timeout_seconds=1800,application_approval=False,full247_authorized=False)

    def raw(self):
        rows=self.config['plan']['scopes'][subject.prepared.PILOT]['branch']
        lines=['CHECKSUM: "666919648 156003475"','INSTANCE: '+subject.prepared.PILOT]
        for r in rows:
            if not r['target']:continue
            p=r['point']; gen=p['attributes'].get('generate_info')
            annotation=subject.ANNOTATION if gen is None else 'vcs_gen_start:'+gen+':vcs_gen_end:'+subject.ANNOTATION
            lines += ['ANNOTATION: "'+annotation+'"',
                'Branch %s "%s" "%s" (%s) "SYNTHETIC_UNIT_FIXTURE_ONLY"' % (
                    p['native_id'],p['attributes']['chksum'],subject.quoted(p['expressions'][0]['exprstr']),p['vector'])]
        return ('\n'.join(lines)+'\n').encode()

    def test_exact3_full100_contract(self):
        subject.validate_config(self.config)
        c=copy.deepcopy(self.config);c['full247_authorized']=True
        with self.assertRaises(ValueError):subject.validate_config(c)
        c=copy.deepcopy(self.config);c['plan']['scopes'][subject.prepared.PILOT]['branch'].pop()
        with self.assertRaises(ValueError):subject.validate_config(c)

    def test_native3_full_fields_sorted_and_generate_binding(self):
        rows=subject.bind_native(self.raw(),self.config)
        self.assertEqual(len(rows),3)
        self.assertEqual({r['point'] for r in rows},{'Branch 15 (0)','Branch 15 (4)','Branch 18 (0)'})
        self.assertTrue(any('i=0' in r['native_annotation'] for r in rows))

    def test_extra_wrong_scope_checksum_expression_generate_rejected(self):
        raw=self.raw()
        for mutated in (raw+b'Toggle x "logic x"\n',
                        raw.replace(subject.prepared.PILOT.encode(),b'wrong_scope'),
                        raw.replace(b'"666919648 156003475"',b'"1 156003475"'),
                        raw.replace(b'"869650179"',b'"1"'),
                        raw.replace(b'"1\'b0"',b'"1\'b1"'),
                        raw.replace(b'i=0:vcs_gen_end:',b'i=1:vcs_gen_end:')):
            with self.subTest(mutated=mutated[-80:]),self.assertRaises(ValueError):
                subject.bind_native(mutated,self.config)

    def test_no_authorization_never_claims_or_launches(self):
        with patch.object(subject,'config_read') as read:
            with self.assertRaises(ValueError):subject.run(Path('/unused'),None,False)
            read.assert_not_called()

    def test_one_shot_second_attempt_never_relaunches(self):
        with tempfile.TemporaryDirectory(dir=subject.prepared.static.OUT) as directory:
            out=Path(directory);(out/'status.json').write_text('{"status":"PREPARED_NO_DVE"}')
            with patch.object(subject,'config_read',return_value=self.config),patch.object(subject,'private') as private:
                private.return_value=lambda *a:None
                subject.run(out,'synthetic-unit-seal',True)
                with self.assertRaises(FileExistsError):subject.run(out,'synthetic-unit-seal',True)
                self.assertEqual(private.call_count,1)

    def test_actual100_audits_missing_and_protected_change_rejected(self):
        with tempfile.TemporaryDirectory(dir=subject.prepared.static.OUT) as directory:
            path=Path(directory)/'audit.tsv'
            def write(stage, bad=False, missing=False):
                with path.open('w',newline='') as f:
                    writer=csv.writer(f,delimiter='\t');writer.writerow(['scope','metric','coordinate','meta','path','excluded'])
                    rows=self.config['plan']['scopes'][subject.prepared.PILOT]['branch']
                    for r in (rows[:-1] if missing else rows):
                        sid,vid=r['coordinate'].split(',');meta='Branch'+sid+'.'+vid
                        value=int(stage in ('selected','reloaded') and r['target'])
                        if bad and not r['target']:value=1
                        writer.writerow([subject.prepared.PILOT,'branch',r['coordinate'],meta,'Item'+sid+'.'+meta,value])
            identities=None
            for stage in subject.STAGES:
                write(stage);identities=subject.audit_states(path,self.config,stage,identities)
            self.assertEqual(len(identities),100)
            write('selected',bad=True)
            with self.assertRaises(ValueError):subject.audit_states(path,self.config,'selected')
            write('before',missing=True)
            with self.assertRaises(ValueError):subject.audit_states(path,self.config,'before')

    def test_tcl_five_stage_reset_reload_existing_audit(self):
        with tempfile.TemporaryDirectory(dir=subject.prepared.static.OUT) as directory:
            out=Path(directory)
            (out/'branch-library.tcl').write_text(subject.branch_library())
            (out/'selection.tcl').write_text(subject.debug.selection(self.config['plan'])+
                'set rvh_annotation {'+subject.ANNOTATION+'}\nset rvh_capture_gate 0\n')
            (out/'live-ready').write_text('HOST_STUB_ONLY')
            script='''
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(RVH_CAPTURE_SEAL) HOST_STUB_ONLY
set rvh_library_only 1
source {%s}
set library {%s}
source $library
proc dbg_metadata {scope metric} {
    global dbg_keys
    set result {}
    foreach key $dbg_keys($scope|branch) {
        set parts [split $key ,]
        set sid [lindex $parts 0];set vid [lindex $parts 1]
        lappend result $key [list Branch$sid.$vid Item$sid.Branch$sid.$vid]
    }
    return $result
}
proc dbg_select {metric meta} {set ::current $meta}
array set excluded {}
proc gui_exclusion {args} {
    if {[lsearch -exact $args -reset]>=0} {array unset ::excluded;array set ::excluded {};return}
    if {[lsearch -exact $args -recalculate]>=0} {return}
    return [expr {[info exists ::excluded($::current)]}]
}
proc gui_exclude_items {args} {set ::excluded($::current) 1}
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion_file {args} {
    set path [lindex $args [expr {[lsearch -exact $args -file]+1}]]
    if {[lsearch -exact $args -save]>=0} {
        set f [open $path w]
        if {[array size ::excluded]} {
            set values {}
            foreach key [lsort [array names ::excluded]] {lappend values $key $::excluded($key)}
            puts $f $values
        }
        close $f
    } else {
        set f [open $path r];set values [read $f];close $f
        array unset ::excluded;array set ::excluded $values
    }
}
proc exec {args} {return RVH_FIRST_EXACT3_HOST_STUB_ONLY}
# The primitive definitions were loaded above; session sourcing is now a no-op.
set f [open $library w];puts $f {# already-loaded host stub primitives};close $f
rvh_session
gui_exclusion -reset
dbg_audit final 0
dbg_save final-empty.el 1
puts "HOST_STUB_FINAL_EMPTY=[array size excluded]"
''' % (out,subject.TCL,out/'branch-library.tcl')
            result=subprocess.run(['/usr/bin/tclsh'],input=script,text=True,capture_output=True,check=True)
            self.assertEqual(result.stderr,'')
            for stage in subject.STAGES:
                self.assertIn('DBG_AUDIT '+stage+' 100',result.stdout)
            self.assertIn('HOST_STUB_FINAL_EMPTY=0',result.stdout)
            self.assertEqual((out/'first.el').read_bytes(),(out/'second.el').read_bytes())
            for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
                self.assertEqual((out/name).read_bytes(),b'')


if __name__=='__main__':unittest.main()
