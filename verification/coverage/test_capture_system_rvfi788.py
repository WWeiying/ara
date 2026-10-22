import copy
import csv
from pathlib import Path
import subprocess
import tempfile
import unittest

import capture_system_rvfi788 as m


class NativeRVFI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r=m.life.read_bound(m.REVIEW,m.REVIEW_SHA)
        protected=[]
        for p in r['protected']:
            a=p['attributes'];label=a['name']+('[%s:%s]'%(a['left'],a['right']) if p['kind']=='vectornode' else '')
            protected.append(dict(p,label=label))
        cls.c=dict(targets=r['targets'],protected=protected,module_checksum=r['compiled_module']['chksum'])
        cls.text='CHECKSUM: "'+cls.c['module_checksum']+' 3385959260"\nINSTANCE: '+m.review.SCOPE+'\nANNOTATION: "'+m.ANNOTATION+'"\n'
        cls.text+=''.join('Toggle '+p['signal']+' "net '+p['native_name']+'"\n' for p in r['targets'])

    def test_exact_source_fixture788(self):
        self.assertEqual(len(m.records(self.text,self.c)),788)
        self.assertEqual(sum(p['width'] for p in self.c['targets']),22126)
        self.assertEqual(len(self.c['protected']),418)

    def test_native_order(self):
        lines=self.text.splitlines()
        self.assertEqual(m.records(self.text,self.c),m.records('\n'.join(lines[:3]+lines[3:][::-1]),self.c))

    def test_native_duplicate_missing_control(self):
        for text in (self.text+self.text,self.text.rsplit('\n',2)[0]+'\n',
                     self.text+'Toggle clk_i "net clk_i"\n'):
            with self.assertRaises(ValueError):m.records(text,self.c)

    def test_scope_checksum_annotation_type_and_bounds(self):
        p=self.c['targets'][0]
        cases=[self.text.replace('3385959260','3385959261'),self.text.replace(m.review.SCOPE,m.review.SCOPE+'.i_ariane'),
            self.text.replace(m.ANNOTATION,'other'),self.text.replace('"net ','"reg ',1),
            self.text.replace(p['native_name'],p['native_name'].replace('[2:0]','[1:0]'))]
        for text in cases:
            with self.assertRaises(ValueError):m.records(text,self.c)

    def write_inventory(self,out,stage):
        rows=[];active=stage in ('selected','reloaded')
        for p in self.c['targets']:
            rows.append([str(len(rows)+1),'path'+str(len(rows)+1),p['native_name'],p['native_name'],str(int(active))])
        for p in self.c['protected']:
            rows.append([str(len(rows)+1),'path'+str(len(rows)+1),p['label'],p['label'],'0'])
        with (out/('native_'+stage+'.tsv')).open('w') as f:
            w=csv.writer(f,delimiter='\t');w.writerow(['handle','path','meta','name','excluded']);w.writerows(rows)
        return rows

    def test_five_stage_real_full_complement(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);before=None
            for stage in ('before','selected','reset','reloaded','final'):
                self.write_inventory(out,stage);value=m.inventory(out,self.c,stage)
                if before is None:before=value
                else:self.assertEqual(value,before)

    def test_protected_port_or_array_missing_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            for name in ('clk_i','rvfi_probes.instr.wdata'):
                for mutation in ('missing','excluded'):
                    rows=self.write_inventory(out,'selected')
                    row=next(p for p in rows if p[2]==name)
                    if mutation=='missing':rows.remove(row)
                    else:row[4]='1'
                    with (out/'native_selected.tsv').open('w') as f:
                        w=csv.writer(f,delimiter='\t');w.writerow(['handle','path','meta','name','excluded']);w.writerows(rows)
                    with self.assertRaises(ValueError):m.inventory(out,self.c,'selected')

    def tcl(self,body):
        script='set rvfi_test_only 1\nsource {'+str(m.HOOK)+'}\n'+body
        p=subprocess.run(['tclsh'],input='if {[catch {\n'+script+'\n} msg]} {puts stderr $msg;exit 1}\n',
            text=True,capture_output=True,timeout=15)
        return p

    def test_plain_tcl_complete_target_match(self):
        p=self.tcl('set names {};set rows {};for {set i 0} {$i<788} {incr i} {lappend names n$i;lappend rows [list p$i m$i n$i]}\nrvfi_validate_rows $rows $names\nputs PASS')
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('PASS',p.stdout)

    def test_plain_tcl_duplicate_missing_foreign(self):
        for mutation in ('set rows [lrange $rows 1 end]', 'lset rows 0 [lindex $rows 1]', 'lset rows 0 {p m foreign}'):
            p=self.tcl('set names {};set rows {};for {set i 0} {$i<788} {incr i} {lappend names n$i;lappend rows [list p$i m$i n$i]}\n'+mutation+'\nrvfi_validate_rows $rows $names')
            self.assertNotEqual(p.returncode,0)

    def test_plain_tcl_wrong_singleton_readback(self):
        p=self.tcl('proc gui_list_get_selected {args} {if {[lsearch $args -count]>=0} {return 0};return {}}\nproc gui_list_select {args} {}\ndw_select actual metadata')
        self.assertNotEqual(p.returncode,0);self.assertIn('singleton',p.stderr)

    def test_plain_tcl_import_review_rejected(self):
        p=self.tcl('set env(DVE_COVERAGE_OUTPUT) /tmp\nproc gui_exclusion_file {args} {}\nproc gui_exclusion {args} {}\nproc gui_cov_excl_review {args} {return 0}\ndw_load first.el')
        self.assertNotEqual(p.returncode,0);self.assertIn('review unresolved',p.stderr)

    def test_plain_tcl_save_requires_real_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.tcl('set env(DVE_COVERAGE_OUTPUT) {'+tmp+'}\nproc gui_exclusion_file {args} {set path [lindex [lindex $args end] 0];set f [open $path w];puts $f extra;close $f}\ndw_save empty.el 1')
            self.assertNotEqual(p.returncode,0);self.assertIn('Nonempty global',p.stderr)


if __name__=='__main__':unittest.main()
