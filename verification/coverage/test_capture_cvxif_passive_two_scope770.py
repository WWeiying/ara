import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import capture_cvxif_passive_two_scope770 as c


class Capture(unittest.TestCase):
    def config(self):
        return dict(scopes=list(c.SCOPES), metrics=list(c.METRICS), protected_metrics=list(c.PROTECTED),
                    root=c.ROOT, recursive=False, timeout_seconds=900, native_qualified=False,
                    population_application=False, pins={}, compiled_scopes=[dict(scope=s,design_module_checksum='12',
                        typed_inventory=[['node','foo','1','1','0',None,None]]) for s in c.SCOPES],
                    metric_checksums={s:['34'] for s in c.SCOPES})

    def el(self):
        return 'CHECKSUM: "12 34"\nANNOTATION: '+json.dumps(c.ANNOTATION)+'\nINSTANCE:'+c.SCOPES[0]+'\nToggle foo\n'

    def test_contract(self): c.contract(self.config())

    def test_contract_negative(self):
        for key,value in [('scopes',[c.ROOT]),('metrics',['Assert']),('recursive',True),
                          ('native_qualified',True),('population_application',True),('timeout_seconds',1800)]:
            cfg=self.config(); cfg[key]=value
            with self.subTest(key=key), self.assertRaises(Exception): c.contract(cfg)

    def test_code_el(self): self.assertEqual(len(c.parse_el(self.el(),self.config())),1)

    def test_el_reject_noncode_and_scopeonly(self):
        for text in [self.el().replace('Toggle foo','Assert foo'), self.el().replace('Toggle foo','Group foo'),
                     self.el().replace('12 34','12'),self.el().replace(c.SCOPES[0],c.ROOT),
                     self.el().replace(c.ANNOTATION,'foreign'), self.el()+'Toggle foo\n',
                     self.el().replace('Toggle foo','Toggle *'),self.el().replace('12 34','99 34')]:
            with self.subTest(text=text),self.assertRaises(Exception): c.parse_el(text,self.config())

    def test_snapshot(self):
        self.assertEqual(c.rows('path\tmeta\tname\texcluded\tcells\np\tm\tn\t0\t100%\n'),{('p','m','n'):('0','100%')})

    def test_snapshot_negative(self):
        for text in ['path\tmeta\tname\texcluded\tcells\np\tm\tn\t2\tx\n',
                     'path\tmeta\tname\texcluded\tcells\np\tm\tn\t0\tx\np\tm\tn\t0\tx\n',
                     'path\tmeta\tname\texcluded\tcells\np\tm\tn\t0\n']:
            with self.assertRaises(Exception): c.rows(text)

    def test_real_compressed_shape_decoder(self):
        sample=c.life.read_bound(c.SAMPLE,c.SAMPLE_SHA)
        p=Path(sample['design'])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
        tree=c.local.primitive.toggle.xml(p)
        for name in ('ara_cvxif_dut_bind','ara_cvxif_if'):
            self.assertTrue(any(n.get('name')==name and n.get('chksum') for n in tree.iter()))

    def test_no_launch_authority(self):
        with self.assertRaises(Exception): c.run(Path('/unused'), 'unused', False)

    def fixture(self,out):
        (out/'DVEfiles').mkdir()
        (out/'DVEfiles/dve_gui.log').write_text('CVXIF_TWO_SCOPE_DONE\n')
        (out/'terminal.json').write_text(json.dumps(dict(returncode=0,timeout=False,actual_dve=[dict(pid=1)])))
        for name in ('initial-empty.el','reset-empty.el','final-empty.el'): (out/name).write_text('')
        for name in ('first.el','second.el'): (out/name).write_text(self.el())
        for stage in c.STAGES:
            (out/(stage+'_availability.json')).write_text(json.dumps({m:True for m in c.METRICS+c.PROTECTED}))
            for metric in c.METRICS+c.PROTECTED:
                for n in range(2 if metric in c.METRICS else 1):
                    flag='1' if metric in c.METRICS and stage in ('selected','reloaded') else '0'
                    (out/(stage+'_'+metric+'_'+str(n)+'.tsv')).write_text(
                        'path\tmeta\tname\texcluded\tcells\np\tm\tfoo\t'+flag+'\t100%\n')
                    (out/(stage+'_'+metric+'_'+str(n)+'.columns')).write_text('Name Coverage\n')

    def test_five_stage_positive(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d); self.fixture(out)
            with patch.object(c,'check',return_value=self.config()): c.verify(out,'synthetic')
            q=json.loads((out/'capture-result.json').read_text())
            self.assertFalse(q['population_application']); self.assertTrue(q['final_reset'])

    def test_five_stage_protected_and_terminal_negative(self):
        changes=[('selected_Assert_0.tsv','path\tmeta\tname\texcluded\tcells\np\tm\tfoo\t1\t100%\n'),
                 ('reloaded_Group_0.tsv','path\tmeta\tname\texcluded\tcells\np\tm\tfoo\t0\t99%\n'),
                 ('final_Toggle_0.tsv','path\tmeta\tname\texcluded\tcells\np\tm\tfoo\t1\t100%\n'),
                 ('selected_Toggle_0.tsv','path\tmeta\tname\texcluded\tcells\n'),
                 ('selected_Line_0.columns','Changed Columns\n'),('final-empty.el','INSTANCE:foreign\n'),
                 ('terminal.json',json.dumps(dict(returncode=1,timeout=False,actual_dve=[{}]))),
                 ('before_availability.json',json.dumps({m:False for m in c.METRICS+c.PROTECTED}))]
        for name,value in changes:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                out=Path(d); self.fixture(out); (out/name).write_text(value)
                with patch.object(c,'check',return_value=self.config()),self.assertRaises(Exception): c.verify(out,'synthetic')

    def test_actual_tcl_source_and_exact_ten_commands(self):
        entry=(c.HERE/'capture_cvxif_passive_two_scope770.tcl').read_text()
        script='set ::cv_test_only 1\n'+entry+'''
set ::cv_scopes [list {a.bind} {a.bind.cvxif}]
set ::cv_annotation {literal [error injection] {braces} ; spaces}
set ::commands {}
proc p740_root {} {}
proc p740_select {scope} {set ::scope $scope}
proc gui_exclude_items {args} {lappend ::commands [list $::scope $args]}
proc gui_exclusion {args} {}
proc gui_process_events {args} {}
proc gui_cov_excl_review {args} {return 1}
cv_apply
if {[llength $::commands] != 10} {error count}
foreach record $::commands {
 set args [lindex $record 1]
 if {[llength $args] != 7 || [lsearch -exact $args -recursive] >= 0} {error options}
 if {[lindex $args 6] ne $::cv_annotation} {error annotation}
 if {[lsearch -exact {Line Condition Branch FSM Toggle} [lindex $args 4]] < 0} {error metric}
}
puts TEN_EXACT_COMMANDS
'''
        r=subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=10)
        self.assertEqual(r.stderr,''); self.assertIn('TEN_EXACT_COMMANDS',r.stdout)
        self.assertNotIn('{*}',entry); self.assertNotIn('rename gui_',entry)


if __name__=='__main__': unittest.main()
