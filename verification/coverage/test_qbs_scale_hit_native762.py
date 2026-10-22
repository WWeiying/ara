import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import qbs_scale_hit_native762 as native


def fixture():
    p = json.loads(native.PROOF.read_bytes())
    scopes = sorted(p['missing_direction_accounting'])
    instances = []
    for scope in scopes:
        selected = {}
        for t in p['targets']:
            if t['scope'] == scope: selected.setdefault(t['signal'],[]).append(t['bit'])
        instances.append(dict(scope=scope,design_module_checksum='123',toggle_checksum='3657545390',
            signals=[dict(name=n,bits=sorted(b),scalar=False,left=31,right=0,native_label=n+'[31:0]')
                     for n,b in sorted(selected.items())]))
    return dict(instances=instances)


class ExactNativeTests(unittest.TestCase):
    def setUp(self):
        self.c = fixture()
        self.text = native.primitive.candidate(self.c)

    def test_exact120_bit240_direction_set(self):
        self.assertEqual(len(native.parse_el(self.text,self.c)),240)
        self.assertEqual(len(self.c['instances'][0]['signals']),15)
        self.assertEqual(self.c['instances'][1]['signals'],[])

    def test_wire_net_signature_equivalent(self):
        for decl in ('wire','net'):
            text = self.text
            for s in self.c['instances'][0]['signals']:
                for bit in s['bits']:
                    text = text.replace(s['name']+' ['+str(bit)+']',
                                        s['name']+' ['+str(bit)+'] "'+decl+' '+s['name']+'[31:0]"')
            self.assertEqual(native.parse_el(text,self.c),native.parse_el(self.text,self.c))

    def test_reg_decl_rejected(self):
        name = self.c['instances'][0]['signals'][0]['name']
        with self.assertRaises(ValueError):
            native.parse_el(self.text.replace(name+' [17]',name+' [17] "reg '+name+'[31:0]"'),self.c)

    def test_bounds_decl_rejected(self):
        name = self.c['instances'][0]['signals'][0]['name']
        with self.assertRaises(ValueError):
            native.parse_el(self.text.replace(name+' [17]',name+' [17] "net '+name+'[30:0]"'),self.c)

    def test_whole_vector_rejected(self):
        with self.assertRaises(ValueError): native.parse_el(self.text.replace(' [17]',''),self.c)

    def test_protected_bit_rejected(self):
        with self.assertRaises(ValueError): native.parse_el(self.text.replace(' [17]',' [16]'),self.c)

    def test_bank1_injection_rejected(self):
        text = self.text.replace(self.c['instances'][0]['scope'],self.c['instances'][1]['scope'])
        with self.assertRaises(ValueError): native.parse_el(text,self.c)

    def test_checksum_rejected(self):
        with self.assertRaises(ValueError): native.parse_el(self.text.replace('3657545390','3657545391'),self.c)

    def test_missing_and_duplicate_rejected(self):
        lines = self.text.splitlines()
        line = next(l for l in lines if l.startswith('Toggle'))
        for changed in (self.text.replace(line+'\n','',1),self.text.replace(line,line+'\n'+line,1)):
            with self.assertRaises(ValueError): native.parse_el(changed,self.c)

    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError): native.parse_el(self.text.replace('Toggle 0to1','Branch'),self.c)

    def test_real_frozen_tcl_five_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            labels = [s['native_label'] for s in self.c['instances'][0]['signals']]
            lines = ['set qc_design mock','set qc_vdb mock','set qc_test mock',
                     'set qc_python mock','set qc_helper mock','set qc_instances {}',
                     'lappend qc_instances [list bank0 [list '+' '.join('{'+n+'}' for n in labels)+']]',
                     'lappend qc_instances [list bank1 {}]']
            (out/'selection.tcl').write_text('\n'.join(lines)+'\n')
            (out/'candidate.el').write_text(self.text)
            script = '''
set ::env(DVE_COVERAGE_OUTPUT) {%s}
set ::names [list %s {write_be[0][0][0][31:0]}]
set ::open_count 0
set ::content ""
proc gui_open_cov {args} {incr ::open_count}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclusion {args} {if {[lindex $args 0] eq "-reset"} {set ::content ""}}
proc gui_exclusion_file {args} {
    set file [lindex $args [expr {[lsearch -exact $args -file]+1}]]
    if {[lindex $args 0] eq "-load"} {
        set f [open $file r]; set ::content [read $f]; close $f
    } else {set f [open $file w];puts -nonewline $f $::content;close $f}
}
proc gui_list_get {args} {
    set op [lindex $args 2]
    if {$op eq "-firstChild"} {
        if {[llength $args] == 3} {return 1};return 0
    }
    set id [lindex $args end]
    if {$op eq "-nextSibling"} {
        if {$id < [llength $::names]} {return [expr {$id+1}]};return 0
    }
    if {$op eq "-path"} {return [lindex $::names [expr {$id-1}]]}
    if {$op eq "-meta"} {return leaf}
    if {$op eq "-text"} {
        if {[lindex $args 3] == 0} {return [lindex $::names [expr {$id-1}]]};return 0
    }
    error "Unknown native mock call $args"
}
rename exec native_exec
proc exec {args} {return {"bit_directions":240}}
proc gui_exit {args} {}
source {%s}
if {$::open_count != 1} {error "Unexpected duplicate database open"}
''' % (out,' '.join('{'+n+'}' for n in labels),native.HERE/'queue_constant_native.tcl')
            result = subprocess.run(['tclsh'],input=script,text=True,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('QUEUE_CONSTANT_NATIVE_FAILED',result.stdout+result.stderr)
            self.assertEqual(result.stdout.count('QUEUE_CONSTANT_NATIVE_DONE'),1)
            for stage in ('before','selected','reset','reloaded','final'):
                for bank in (0,1): self.assertTrue((out/('native_%s_%d.tsv'%(stage,bank))).is_file())
            for name in ('initial-empty.el','reset-empty.el','final-empty.el'):
                self.assertEqual((out/name).read_bytes(),b'')
            self.assertEqual(native.parse_el((out/'first.el').read_text(),self.c),
                             native.parse_el((out/'second.el').read_text(),self.c))


if __name__ == '__main__': unittest.main()
