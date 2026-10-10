import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
import report_native_full775 as p


class Full775Tests(unittest.TestCase):
    def test_actual_qualified_native_parsers(self):
        m=p.life.read_bound(p.MFPU/'capture-result.json',p.MFPU_SHA)
        mc=p.life.read_bound(p.MFPU/'config.json',m['config_seal'])
        self.assertEqual(len(p.mfpu.el_members((p.MFPU/'first.el').read_text(),mc)),34816)
        q=p.life.read_bound(p.RVH_CLOSURE,p.RVH_SHA)
        rc=p.life.read_bound(p.rvh.OUT/'config.json',q['original_config_sha256'])
        self.assertEqual(len(p.rvh.native.records((p.rvh.OUT/'first.el').read_text(),rc)),79)

    def test_actual_native_source_partition(self):
        m=p.life.read_bound(p.MFPU/'capture-result.json',p.MFPU_SHA); mc=p.life.read_bound(p.MFPU/'config.json',m['config_seal'])
        q=p.life.read_bound(p.RVH_CLOSURE,p.RVH_SHA); rc=p.life.read_bound(p.rvh.OUT/'config.json',q['original_config_sha256'])
        c={'mfpu775':{'config':mc},'rvh775':{'config':rc}}
        old=(p.PREP773/'combined.el').read_text(); a=(p.MFPU/'first.el').read_text(); b=(p.rvh.OUT/'first.el').read_text()
        split=p.partition(old+a+b,p.wanted(c))
        self.assertEqual(p.prior.branch.native_inventory(split['retained'].encode()),p.prior.branch.native_inventory(old.encode()))
        self.assertEqual(p.mfpu.el_members(split['mfpu'],mc),p.mfpu.el_members(a,mc))
        self.assertEqual(p.rvh.native.records(split['rvh'],rc),p.rvh.native.records(b,rc))

    def test_metric_and_whole_observer_not_lost(self):
        a='CHECKSUM: "1"\nINSTANCE: s\n'
        b='CHECKSUM: "1 2"\nINSTANCE: t\nBranch x "x"\nToggle y "logic y"\n'
        result=p.partition(a+b,{'mfpu':{('t','y')},'rvh':set()})
        self.assertIn(a,result['retained']);self.assertIn('Branch x',result['retained'])
        self.assertNotIn('Toggle y',result['retained']);self.assertIn('Toggle y',result['mfpu'])

    def test_duplicate_owner_rejected(self):
        with self.assertRaises(ValueError):p.partition('CHECKSUM: "1 2"\nINSTANCE: s\nToggle x "logic x"\n',{'a':{('s','x')},'b':{('s','x')}})

    def test_array_owner_prefix_exact(self):
        approved={('s','a[2]')}
        self.assertTrue(p.owns('s','a','arrays',approved))
        self.assertFalse(p.owns('s','ab','arrays',approved))
        self.assertFalse(p.owns('s','a','vectornode',approved))

    def test_strict_per_object_flags_and_complement(self):
        e=[dict(name='x',labels=['x[0]'],kind='vectornode',target=True),dict(name='y',labels=['y'],kind='node',target=False)]
        rows=[dict(handle=str(i+1),path=label,meta=label,name=label,excluded=flag) for i,(label,flag) in enumerate([('x[0]','1'),('y','0')])]
        p.row_gate(rows,e,True,set(),'s','selected')
        for mutation in ('excluded','path','handle'):
            b=copy.deepcopy(rows);b[1][mutation]=b[0][mutation]
            with self.assertRaises(ValueError):p.row_gate(b,e,True,set(),'s','selected')
        with self.assertRaises(ValueError):p.row_gate(rows[:1],e,True,set(),'s','selected')

    def test_old_qualified_owner_only(self):
        e=[dict(name='counter',labels=['counter[31:0]'],kind='vectornode',target=False)]
        rows=[dict(handle='1',path='counter[31:0]',meta='counter[31:0]',name='counter[31:0]',excluded='1')]
        p.row_gate(rows,e,True,{('s','counter')},'s','selected')
        with self.assertRaises(ValueError):p.row_gate(rows,e,True,{('other','counter')},'s','selected')
        with self.assertRaises(ValueError):p.row_gate(rows,e,False,{('s','counter')},'s','reset')

    def test_full_or_and_missing_scope(self):
        rows={str(i):dict(width=1,checksum='1',bits='0') for i in range(6162)}
        old=dict(tests=['a'],design={'x':'y'},metrics={'m':rows})
        new=dict(old,tests=['a','b']);single=dict(old,tests=['b'])
        p.population(old,new,single,2)
        bad=copy.deepcopy(new);bad['metrics']['m']['0']['bits']='1'
        with self.assertRaises(ValueError):p.population(old,bad,single,2)
        bad=copy.deepcopy(new);del bad['metrics']['m']['0']
        with self.assertRaises(ValueError):p.population(old,bad,single,2)

    def test_prefix_duplicate_and_design_drift(self):
        rows={str(i):dict(width=1,checksum='1',bits='0') for i in range(6162)}
        old=dict(tests=['a'],design={'x':'y'},metrics={'m':rows});single=dict(old,tests=['b'])
        for tests in (['a','a'],['c','b']):
            with self.assertRaises(ValueError):p.population(old,dict(old,tests=tests),single,2)

    def test_real_hook_inside_proc_does_not_open_second_db(self):
        with tempfile.TemporaryDirectory() as directory:
            text=r'''
set ::env(DVE_COVERAGE_OUTPUT) {@OUT@}
rename source actual_source
proc source {path} {
 if {[file tail $path] eq "report_native_full773_branch720.tcl"} {
  proc combo_audit {stage mode active} {set ::active $active}
  proc p740_root {} {}
  proc p740_select {scope} {return $scope}
  proc dw_select {path meta} {set ::selected $meta}
 } else {uplevel 1 [list actual_source $path]}
}
proc imported_inside_proc {} {actual_source {@TCL@}}
imported_inside_proc
set ::full775_mfpu_scopes [list s]
set ::full775_rvh_scopes [list t]
proc gui_open_cov {args} {error "Unexpected second database open"}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_get_property {args} {
 set n [lindex $args end]; if {$n>=4} {error end}
 return [lindex {Variable Type Coverage Display} $n]
}
proc gui_list_get {args} {
 set i [lsearch -exact $args -text]
 if {$i>=0} {return [lindex {x signal 0.00% 0} [lindex $args [expr {$i+1}]]]}
 if {[lsearch -exact $args -firstChild]>=0} {if {[llength $args]==3} {return 1};return 0}
 if {[lsearch -exact $args -nextSibling]>=0} {return 0}
 return x
}
proc gui_exclusion {args} {return $::active}
foreach {stage mode active} {initial before 0 applied selected 1 reset reset 0 reloaded reloaded 1 final final 0} {
 combo_audit $stage $mode $active
}
puts FULL775_HOST_PASS
'''.replace('@OUT@',directory).replace('@TCL@',str(p.TCL))
            r=subprocess.run(['tclsh'],input=text,text=True,capture_output=True,timeout=15)
            self.assertEqual(r.stderr,'');self.assertEqual(r.returncode,0);self.assertIn('FULL775_HOST_PASS',r.stdout)
            for stage in p.STAGES:
                for family in ('mfpu','rvh'):
                    rows=(Path(directory)/('%s775_%s_0.tsv'%(family,stage))).read_text().splitlines()
                    self.assertEqual(len(rows),2);self.assertEqual(rows[1].split('\t')[-1],str(int(stage in ('selected','reloaded'))))


if __name__=='__main__':unittest.main()
