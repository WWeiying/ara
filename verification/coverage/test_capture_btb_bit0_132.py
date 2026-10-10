import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import capture_btb_bit0_132 as c


class NativeAuthority(unittest.TestCase):
    def test_complete_pairs_header_order_and_sole_range(self):
        lines=c.plan.el_text().splitlines()
        reordered='\n'.join([lines[0],lines[2],lines[1]]+lines[3:]).replace(' [0] ', ' [0:0] ')
        self.assertEqual(c.native_records(reordered),c.plan.records(c.plan.el_text()))
        pairs=[]
        for line in lines[3:]:
            pairs.extend(line.replace('Toggle ','Toggle '+d+' ',1) for d in ('0to1','1to0'))
        self.assertEqual(len(c.native_records('\n'.join(lines[:3]+pairs))),132)
        with self.assertRaises(ValueError):c.native_records('\n'.join(lines[:3]+pairs[:-1]))

    def test_expansion_duplicate_foreign_metric_and_scope(self):
        text=c.plan.el_text()
        mutations=[text.replace(' [0] ',' ',1),text.replace(' [0] ',' [1] ',1),
            text.replace(' [0] ',' [0:1] ',1),text+text.splitlines()[3]+'\n',
            text+'Transition x "A" -> "B"\n',text.replace(c.plan.SCOPE,c.plan.SCOPE+'.child'),
            text.replace(c.plan.CHECKSUM,'0 1574888635'),
            text.replace('btb_prediction_o[0].target_address','btb_prediction_o[0].valid')]
        for text in mutations:
            with self.subTest(text=text[-80:]),self.assertRaises(ValueError):c.native_records(text)

    def test_real_typed_complement_all_valid_and_control(self):
        inventory=json.loads((c.STATIC/'inventory.json').read_bytes())
        kept=c.complement(inventory)
        self.assertEqual(len(kept),8860)
        for n in inventory['all_nodes']:
            name=n['attrs']['name']
            for bit in range(n['width']):
                for direction in ('0to1','1to0'):
                    self.assertEqual((name,bit,direction) in kept,not(name in c.plan.NAMES and bit==0))

    def test_percent_native_actual_encoding_strict(self):
        self.assertEqual(c.percent('98.35%'),c.percent('98.35'))
        for value in ('98.35%%',' 98.35%','NaN','-1','1e2','100.01','01.0',''):
            with self.subTest(value=value),self.assertRaises(ValueError):c.percent(value)


class EntryPipeline(unittest.TestCase):
    def fixture(self,out):
        inventory=json.loads((c.STATIC/'inventory.json').read_bytes())
        pin=out/'sealed-input';pin.write_text('sealed')
        config=dict(schema='BTB_BIT0_132_LOCAL_NATIVE_PREPARED', output=str(out),population=779,
            static_seal=c.STATIC_SHA,baseline_seal=c.plan.BASE_SHA,scope=c.plan.SCOPE,
            timeout_seconds=600,automatic_retry=False,population_application=False,
            design=str(c.plan.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'),
            vdb=str(c.RUN/'code.vdb'),selected_test=str(c.RUN/'code/btb_target_ring_sv39'),
            inventory=inventory,identity=dict(executable='/sealed/mock/dve.exe'),
            pins={str(pin):c.digest(pin),str(c.STATIC/'inventory.json'):c.digest(c.STATIC/'inventory.json')})
        c.save(out/'config.json',config);seal=c.digest(out/'config.json')
        c.save(out/'candidate.el',c.plan.el_text())
        c.save(out/'live-ready','LIVE_EXECUTABLE_VERIFIED\n')
        vals=dict(btb_design=config['design'],btb_vdb=config['vdb'],btb_test=config['selected_test'],
            btb_scope=config['scope'],btb_python=str(c.plan.ROOT/'verification/tools/soc-venv/bin/python'),
            btb_helper=str(Path(c.__file__).resolve()))
        c.save(out/'selection.tcl',''.join('set ::%s {%s}\n'%item for item in vals.items()))
        names=[n['attrs']['name'] for n in inventory['all_nodes']]
        return config,seal,names

    def pipeline(self,out,mutation=''):
        config,seal,names=self.fixture(out)
        script='''
set env(DVE_COVERAGE_OUTPUT) {%s}
set env(BTB132_CONFIG_SEAL) {%s}
set ::names [list %s]
set ::state {OLD_SCOPE_EXCLUSION}
set ::mutation {%s}
set ::loaded 0
proc gui_open_cov {args} {
    if {[lindex $args 1] ne $::btb_design || [lindex $args 3] ne [list $::btb_vdb] ||
        [lindex $args 5] ne [list $::btb_test]} {error "Open test contract"}
}
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args 2] 0]
    if {[lindex $args 0] eq "-save"} {
        set s [open $path w];puts -nonewline $s $::state;close $s
    } else {
        set s [open $path r];set ::state [read $s];close $s
        incr ::loaded
        if {$::loaded == 2 && $::mutation eq "reload"} {
            set ::state [string map [list { [0] } { [1] }] $::state]
        }
    }
}
proc gui_exclusion {args} {if {[lindex $args 0] eq "-reset"} {set ::state ""}}
proc gui_cov_excl_review {args} {return [expr {$::mutation ne "rejected"}]}
proc gui_covtable_show {args} {}
proc gui_cov_show_value {args} {}
proc gui_covtable_setroot {args} {
    if {[lindex $args 2] ne $::btb_scope} {error "Only bound root permitted"}
}
proc gui_process_events {args} {}
proc gui_list_expand {args} {
    if {[lindex $args 1] ne "CovDetail.1"} {error "No full hierarchy traversal permitted"}
}
proc gui_list_action {args} {
    if {[lindex $args end] ne "i_btb"} {error "Rooted context token"}
}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get_property {args} {
    set index [expr {[lindex $args 3]-5}]
    if {$index >= 6} {error End}
    return [lindex {Score Line Toggle FSM Condition Branch} $index]
}
proc gui_list_get {args} {
    set id [lindex $args 1];set op [lindex $args 2]
    if {$id eq "CoverageTable.1"} {
        if {$op eq "-firstChild"} {return 1}
        if {$op eq "-nextSibling"} {return 0}
        if {$op eq "-path" || ($op eq "-text" && [lindex $args 3] == 0)} {
            if {$::mutation eq "root"} {return foreign};return i_btb
        }
        if {$op eq "-text"} {
            set column [lindex $args 3]
            if {$column == 5 || $column == 7} {if {$::state ne ""} {return 99.99%%};return 98.35%%}
            return 50.00%%
        }
    } else {
        if {$op eq "-firstChild"} {if {[llength $args] == 3} {return 1};return 0}
        set item [lindex $args end]
        if {$op eq "-nextSibling"} {if {$item < [llength $::names]} {return [expr {$item+1}]};return 0}
        if {$op eq "-path" || $op eq "-meta" || $op eq "-text"} {
            return [lindex $::names [expr {$item-1}]]
        }
    }
    error "Unmocked native API $args"
}
# Source through an actual proc, matching DVE namespace boundaries; the driver
# must explicitly source selection globally and exit on failure.
proc entry {} {source {%s}}
entry
puts MUST_NOT_CONTINUE_AFTER_EXIT
'''%(out,seal,' '.join('{'+n+'}' for n in names),mutation,c.HOOK)
        result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,cwd=out,timeout=30)
        return config,seal,result

    def test_real_standalone_five_stage_entry_and_original_state_clear(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);config,seal,result=self.pipeline(out)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(result.stdout.splitlines().count('BTB132_NATIVE_DONE'),1)
            self.assertNotIn('MUST_NOT_CONTINUE',result.stdout)
            self.assertEqual((out/'inherited-before-clear.el').read_text(),'OLD_SCOPE_EXCLUSION')
            for stage in c.STAGES:
                self.assertEqual(len(c.check_stage(out,config,stage)),132 if stage in ('applied','reloaded') else 0)
                c.metrics(out,stage)
            self.assertEqual(c.inventory_rows(out,config,'before'),c.inventory_rows(out,config,'final'))
            live=[dict(pid=123,starttime=101,launch_pid=122,launch_starttime=100,
                       executable=config['identity']['executable'],executable_verified=True)]
            c.save(out/'live-identity.json',live)
            c.save(out/'terminal.json',dict(returncode=0,timeout=False,actual_dve=live))
            (out/'DVEfiles').mkdir();(out/'DVEfiles/dve_gui.log').write_text(result.stdout)
            with patch.object(c.tools,'revalidate'):
                first=c.verify(out,seal)
                self.assertEqual(c.verify(out,seal),first)
            qualified=json.loads((out/'capture-result.json').read_bytes())
            self.assertEqual(qualified['protected_directions'],8860)
            self.assertFalse(qualified['per_bit_GUI_flags_read'])
            self.assertFalse(qualified['population_application'])

    def test_bad_reload_rejected_before_done_with_final_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);_,_,result=self.pipeline(out,'reload')
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)
            self.assertIn('Nonpartial', (out/'error.txt').read_text())
            self.assertNotIn('BTB132_NATIVE_DONE',result.stdout)
            self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_root_and_import_errors_still_independent_cleanup(self):
        for mutation in ('root','rejected'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as temp:
                out=Path(temp);_,_,result=self.pipeline(out,mutation)
                self.assertEqual(result.returncode,1,result.stdout+result.stderr)
                self.assertTrue((out/'error.txt').exists())
                self.assertEqual((out/'cleanup-empty.el').read_bytes(),b'')

    def test_nonempty_reset_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);config,_,_=self.fixture(out)
            (out/'initial-empty.el').write_text(c.plan.el_text())
            with self.assertRaises(ValueError):c.check_stage(out,config,'before')

    def test_no_aggregate_gui_exclusion_evidence(self):
        text=c.HOOK.read_text()
        self.assertNotIn('-excluded',text)
        self.assertNotIn('gui_cov_tgl_double_click',text)
        self.assertNotIn('gui_exit',text.split('proc btb_main')[0])
        self.assertIn('exit 0',text)


class PreparedActualInputs(unittest.TestCase):
    def test_actual_prepare_without_launch(self):
        with tempfile.TemporaryDirectory(dir=c.plan.OUT,prefix='btb132-host-test-') as temp:
            # prepare requires a direct OUT child, so use the temporary path itself
            # after removing the empty directory created by TemporaryDirectory.
            out=Path(temp);out.rmdir()
            seal=c.prepare(out)
            config=c.read_config(out,seal)
            self.assertEqual(len(c.complement(config['inventory'])),8860)
            self.assertEqual(c.native_records((out/'candidate.el').read_text()),c.plan.records(c.plan.el_text()))
            self.assertNotIn('execution.json',[p.name for p in out.iterdir()])
            self.assertEqual(config['population'],779)
            with self.assertRaises(ValueError):c.prepare(out)


if __name__=='__main__':unittest.main()
