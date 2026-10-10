"""Host full session model plus actual exact native signatures. Never launches DVE."""
from collections import Counter
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch

import qbs_eight735_runtime as p


class Combined(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline=p.design.evidence()
        cls.qraw=(p.merge.qualified.RUN/'first.el').read_bytes()
        cls.raw=(p.merge.EIGHT/'applied.el').read_bytes()+cls.qraw
        cls.artifact,cls.original,_,_=p.merge.qualified.native.old.inputs()

    def test_actual7684_identity_protection_and_no_overlap(self):
        self.assertEqual(p.check_union(self.raw),7684)
        self.assertEqual(Counter(r[3] for r in p.merge.records(self.raw)),dict(Branch=5808,Condition=1876))
        self.assertEqual(self.baseline['mutual_review']['native_point_identity_overlap_count'],0)

    def test_exact_union_negative_attributes(self):
        lines=self.raw.splitlines(True)
        for before,after in ((b'Condition 8260 ',b'Condition 999999 '),(b'(3 "11")',b'(3 "10")'),
            (b'4245564008',b'4245564009'),(b' 1 -1',b' 2 -1'),(b'bank0',b'bank9'),
            (b'vcs_gen_start:row=0,b=0:',b'vcs_gen_start:row=1,b=0:')):
            with self.subTest(field=before):
                self.assertIn(before,self.raw)
                mutated=self.raw.replace(before,after,1)
                self.assertNotEqual(mutated,self.raw)
                with self.assertRaises(ValueError):p.check_union(mutated)
        for raw in (self.raw+self.qraw,self.raw[:-100],b''.join(lines[1:]),self.raw+b'\xff\n'):
            with self.subTest(shape=raw[-12:]),self.assertRaises(ValueError):p.check_union(raw)

    def test_render_actual735_selector_and_legacy_library_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);data=p.payloads(out)
            t=tkinter.Tcl();t.tk.wantobjects(False);t.eval(data['qbs-side-selection.tcl'].decode('ascii'))
            self.assertEqual(t.getvar('qs_output'),str(out))
            self.assertEqual(t.eval('array size qn_expected'),'1792')
            self.assertNotIn(b'set failed [catch {eight_initialize;',data['eight-library.tcl'])
            self.assertEqual(p.check_union(data['combined-nine.el']),7684)
            self.assertIn(b'six_expected_count',data['population-selection.tcl'])

    def model(self, out, fault=None):
        """Run complete new entry using audited native QBS audit and old8 call-boundary stubs."""
        t=tkinter.Tcl();t.tk.wantobjects(False)
        t.eval('''foreach cmd {lassign dict lmap try coroutine tailcall apply} {
            if {[llength [info commands $cmd]]} {rename $cmd {}}
        }
        set qe_library_only 1
        ''')
        t.setvar('env(DVE_COVERAGE_OUTPUT)',str(out))
        # The boundary stub preserves the exact frozen tail replaced by the runtime.
        library='''proc eight_initialize {} {
            proc lpd_require {ok message} {if {!$ok} {error $message}}
            proc seven_replace_once {body needle replacement} {
                if {[string first $needle $body]<0 || [string first $needle $body]!=[string last $needle $body]} {error "Boundary differs"}
                return [string map [list $needle $replacement] $body]
            }
            proc qbsapp_root {} {incr ::roots}
            proc qbs_audit {stage active} {lappend ::old8 [list $stage $active]; if {$::fault eq "old8" && $active} {error "Old8 protected changed"}}
            proc dbg_save {name {empty 0}} {
                set path [file join $::env(DVE_COVERAGE_OUTPUT) $name]
                gui_exclusion_file -save -file [list $path]
                if {$empty && [file size $path]!=0} {error "Not global empty"}
            }
            proc qbsapp_session {} {
                global env
                dbg_save initial-empty.el 1
                qbs_audit before 0
                gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) combined-eight.el]]
                qbs_audit selected 1
                dbg_save applied.el
                gui_exclusion -reset
                qbs_audit reset 0
                dbg_save reset-empty.el 1
                gui_exclusion_file -load -file [list [file join $env(DVE_COVERAGE_OUTPUT) applied.el]]
                qbs_audit reloaded 1
                dbg_save reloaded.el
                lpd_require [expr {[lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) applied.el]] eq
        [lpb_bytes [file join $env(DVE_COVERAGE_OUTPUT) reloaded.el]]}] "Combined EL actual reload bytes differ"
                qbsapp_root
                qbs_audit after-root 1
                dbg_save after-root.el
                gui_exclusion -reset
                dbg_save session-final-empty.el 1
            }
        }
        '''
        (out/'eight-library.tcl').write_text(library)
        (out/'csv-row-library.tcl').write_text('proc csv_row {args} {}\n')
        (out/'combined-nine.el').write_bytes(self.raw)
        selector=p.merge.qualified.native.old.selection(self.artifact,self.original,out)
        (out/'qbs-side-selection.tcl').write_text(selector)
        t.eval(p.TCL.read_text());t.setvar('roots','0');t.setvar('old8','');t.setvar('fault',fault or '')
        t.eval('qe_initialize')
        # Reuse captured paths/metas as host mapping fixtures, not numeric evidence fabrication.
        original=(p.merge.qualified.RUN/'native-qualification.tcllist').read_text('ascii')
        objects=[t.splitlist(x) for x in original.splitlines() if x.startswith('object ')]
        for row in objects:t.call('set','hostmeta('+t.call('list',row[1],row[2])+')',row[6])
        t.eval('''proc qbf_scope {scope groups} {
            foreach g $groups {
                set key [list $scope [lindex $g 0]]
                set ::qn_meta($key) $::hostmeta($key)
            }
        }''')
        groups=p.merge.qualified.native.old.full.groups(self.artifact)
        names={};expressions={}
        for g in groups:
            key=t.call('list',g['scope'],g['expression']);meta=t.getvar('hostmeta('+key+')')
            names[g['scope'],meta]=g['names'];expressions[g['scope'],meta]=g['expression']
        state=dict(active=False,scope='',cond='',vector='')
        targets={(g['scope'],g['expression'],v) for g in groups for v in g['targets']}
        def action(*args):state.update(scope=args[-1],cond='',vector='');return ''
        def selected(*args):
            view=args[args.index('-list')+1]
            if '-count' in args:return str(int(bool(state[view])))
            if '-all' in args:return t.call('list',*names[state['scope'],state['cond']])
            return t.call('list',state[view])
        def select(*args):
            view=args[args.index('-list')+1];state[view]='' if '-unselect' in args else t.splitlist(args[-1])[0];return ''
        def exclusion(*args):
            if args==('-reset',):
                if fault!='reset':state['active']=False
                return ''
            if '-recalculate' in args:return ''
            key=state['scope'],expressions[state['scope'],state['cond']],state['vector']
            v=state['active'] and key in targets
            if fault=='neighbor' and state['active'] and key not in targets:v=True
            return str(int(v))
        def el(*args):
            path=Path(t.splitlist(args[-1])[0])
            if '-load' in args:
                self.assertIn(path.name,('combined-nine.el','applied.el'))
                state['active']=True;return ''
            raw=self.raw if state['active'] else b''
            if path.name=='reloaded.el' and raw:
                # Equivalent block reordering is required to pass.
                blocks=list(p.eight.metric.blocks(raw));raw=b''.join(x[1] for x in reversed(blocks))
                if fault=='annotation':raw=raw.replace(b'vcs_gen_start:row=0,b=0:',b'vcs_gen_start:row=1,b=0:',1)
                if fault=='extra':raw+=self.qraw
            path.write_bytes(raw);return ''
        for name,fn in dict(gui_list_action=action,gui_covdetail_query=lambda *a:'Condition',
            gui_list_get_selected=selected,gui_list_select=select,gui_exclusion=exclusion,gui_exclusion_file=el).items():t.createcommand(name,fn)
        try:
            t.eval('qbsapp_session; gui_exclusion -reset; qbsapp_root; qbs_audit final 0; dbg_save final-empty.el 1; dbg_save cleanup-empty.el 1')
            return t.splitlist(t.getvar('old8'))
        finally:t.eval('close $qbf_stream')

    def test_full_entry_six_stages_legacy_actualQBSaudit_and_reorderedUnion(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);stages=self.model(out)
            self.assertEqual([tkinter.Tcl().splitlist(x)[0] for x in stages],list(p.design.STAGES))
            self.assertNotEqual((out/'applied.el').read_bytes(),(out/'reloaded.el').read_bytes())
            self.assertEqual(p.check_union((out/'reloaded.el').read_bytes()),7684)
            rows=(out/'native-qualification.tcllist').read_text().splitlines()
            self.assertEqual(sum(x.startswith('audit ') for x in rows),21504)
            for name in ('initial-empty.el','reset-empty.el','session-final-empty.el','final-empty.el','cleanup-empty.el'):
                self.assertEqual((out/name).read_bytes(),b'')

    def test_full_entry_failures_not_weakened(self):
        for fault in ('old8','neighbor','reset','annotation','extra'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(tkinter.TclError):self.model(Path(tmp),fault)

    def test_source_pin_and_reader_seal_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reader';path.write_bytes(b'original');sha=p.f.sha(path)
            ledger={str(path):sha};p.f.check_pins(ledger);path.write_bytes(b'drift')
            with self.assertRaises(ValueError):p.f.check_pins(ledger)
            with self.assertRaises(ValueError):p.reader_context(path,sha)

    def test_prepare_verify_roundtrip_and_omitted_dependency(self):
        # Isolate the pending external reader, not the runtime pin/render/command gates.
        source=dict(pins={str(p.design.READER):p.design.READER_SHA})
        config=dict(plan=dict(tool_identity={'host_fixture_only':True}))
        deps=(p.SCRIPT,p.TCL,p.TEST)
        command=['/host-fixture/dve','-script',str(p.TCL)]
        with tempfile.TemporaryDirectory() as tmp,patch.object(p.f.proof,'OUT',Path(tmp)),\
             patch.object(p.design,'evidence',return_value=self.baseline),\
             patch.object(p,'reader_context',return_value=(source,None,config)),\
             patch.object(p,'dependencies',return_value=deps),\
             patch.object(p.f.tool,'revalidate'),patch.object(p.f.tool,'launch_command',return_value=command):
            out=Path(tmp)/'fresh'
            seal=p.prepare(out,p.design.READER,p.design.READER_SHA)
            result,_,derived=p.verify(out,seal)
            self.assertEqual(result['budget_seconds'],14400)
            self.assertEqual(derived['output'],str(out))
            self.assertEqual(result['command'][:3],['/usr/bin/timeout','--kill-after=10s','14400s'])
            self.assertFalse(result['launch_approved']);self.assertFalse(result['application_approval'])
            with self.assertRaises(ValueError):p.prepare(out,p.design.READER,p.design.READER_SHA)
            for key,value in (('population',734),('payload_condition_protected',41213),('budget_seconds',3600),
                              ('application_approval',True),('source_control_boundary',{})):
                record=dict(result);record[key]=value
                (out/p.NAME).write_text(p.json.dumps(record))
                with self.subTest(field=key),self.assertRaises(ValueError):p.verify(out,p.f.sha(out/p.NAME))
            record=dict(result);record['pins']=dict(record['pins']);del record['pins'][str(p.TCL)]
            (out/p.NAME).write_text(p.json.dumps(record))
            with self.assertRaises(ValueError):p.verify(out,p.f.sha(out/p.NAME))

    def test_actual_discovery_sixstage_fixture_and_missing_duplicate_protection(self):
        t=tkinter.Tcl();t.tk.wantobjects(False)
        original=(p.merge.qualified.RUN/'native-qualification.tcllist').read_text('ascii').splitlines()
        discovery=[x for x in original if t.splitlist(x)[0] in ('inventory','object','group','scope_complete')]
        allrows=[]
        for stage in p.design.STAGES:
            observed='reloaded' if stage=='after-root' else stage
            for x in original:
                r=t.splitlist(x)
                if r[0] in ('audit','stage') and r[1]==observed:
                    allrows.append(t.call('list',r[0],stage,*r[2:]))
        rows=discovery+allrows+[t.call('list','terminal','0','','')]
        raw=('\n'.join(rows)+'\n').encode('ascii')
        self.assertEqual(p.qbs_rows(raw),21504)
        audit=next(i for i,r in enumerate(rows) if t.splitlist(r)[0]=='audit')
        neighbor=next(i for i,r in enumerate(rows) if t.splitlist(r)[0]=='audit' and
                      t.splitlist(r)[1]=='selected' and t.splitlist(r)[-1]=='0')
        changed=t.splitlist(rows[neighbor]);changed=t.call('list',*changed[:-1],'1')
        for bad in (rows[:audit]+rows[audit+1:],rows[:audit]+[rows[audit]]+rows[audit:],
            rows[:neighbor]+[changed]+rows[neighbor+1:],rows[:-1],rows[:-1]+['terminal 1 failure {}']):
            with self.assertRaises(ValueError):p.qbs_rows(('\n'.join(bad)+'\n').encode('ascii'))


if __name__=='__main__':unittest.main()
