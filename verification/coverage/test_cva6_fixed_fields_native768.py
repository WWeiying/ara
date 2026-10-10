import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import cva6_fixed_fields_native768 as n


def config():
    return dict(instances=[dict(scope='top.decode', design_module_checksum='12', toggle_checksum='34',
        signals=[dict(name='previous[0].pc', bits=[0, 1], scalar=False, left=1, right=0, native_label='previous[0].pc[1:0]')])])


def inventory(target='0.00', retained='97.28', array=True):
    text = 'handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay\n'
    text += '1\tp\tm\tprevious[0].pc[1:0]\tToggle\t'+target+'\t'+target+'\n'
    text += '2\tp2\tm2\tfunctional[63:0]\tToggle\t'+retained+'\t'+retained+'\n'
    if array: text += '3\tpa\tma\tmem[0][31:0]\tMDA\t53.25\t53.25\n'
    return text


class NativeTests(unittest.TestCase):
    def test_exact_candidate_with_bracketed_struct_name(self):
        c = config(); self.assertEqual(len(n.parse_el(n.primitive.candidate(c), c)), 4)

    def test_native_reg_signature_bounds(self):
        c = config()
        text = 'CHECKSUM: "12 34"\nINSTANCE: top.decode\nToggle previous[0].pc "reg previous[0].pc[1:0]"\n'
        self.assertEqual(len(n.parse_el(text, c)), 4)
        with self.assertRaises(ValueError): n.parse_el(text.replace('[1:0]"', '[2:0]"'), c)

    def test_wrong_scope_checksum_metric_duplicate_missing(self):
        c=config(); text=n.primitive.candidate(c)
        for bad in (text.replace('12 34','12 35'), text.replace('top.decode','top.other'),
                    text+'Branch X\n', text+'Toggle 0to1 previous[0].pc [0]\n',
                    '\n'.join(text.splitlines()[:-1])):
            with self.subTest(bad=bad), self.assertRaises(ValueError): n.parse_el(bad, c)

    def test_low32_bit_retained(self):
        c=config(); s=c['instances'][0]['signals'][0]
        s.update(name='instruction_o.result', left=63, right=0, bits=list(range(32,64)), native_label='instruction_o.result[63:0]')
        self.assertEqual(len(n.parse_el(n.primitive.candidate(c),c)),64)
        with self.assertRaises(ValueError): n.parse_el('CHECKSUM: "12 34"\nINSTANCE: top.decode\nToggle instruction_o.result\n',c)

    def instance(self):
        i=config()['instances'][0]
        i['all_typed_labels']=['previous[0].pc[1:0]','functional[63:0]','mem[0:0][31:0]']
        return i

    def stages(self):
        return {s:inventory('100.00' if s in ('selected','reloaded') else '0.00')
                for s in ('before','selected','reset','reloaded','final')}

    def test_actual_percentage_forms_and_array_singleton(self):
        self.assertEqual(n.audit_native(self.instance(), self.stages()), (3,2))
        for value in ('0.00','53.25','97.28','100.00','100.00%','--',''):
            n.native_rows(inventory(retained=value))

    def test_protected_percentage_changed(self):
        stages=self.stages();stages['selected']=inventory('100.00','97.29')
        with self.assertRaises(ValueError): n.audit_native(self.instance(),stages)

    def test_missing_array_and_wrong_reset(self):
        for bad in (inventory(array=False),inventory('100.00')):
            stages=self.stages();stages['reset']=bad
            with self.assertRaises(ValueError): n.audit_native(self.instance(),stages)

    def test_percent_not_capacity_or_blank_column_assumption(self):
        for value in ('101.0','-1','nan','1536/2048'):
            with self.assertRaises(ValueError): n.native_rows(inventory(retained=value))
        with self.assertRaises(ValueError): n.native_rows(inventory().replace('coverage','column1'))

    def test_actual_source_guards(self):
        proof=json.loads(n.PROOF.read_bytes()); self.assertEqual(n.source_guard(proof)['FpgaAlteraEn'],0)
        original=Path.read_text
        def read(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            return text.replace("FpgaAlteraEn: bit'(0)","FpgaAlteraEn: bit'(1)")
        with patch.object(Path,'read_text',read), self.assertRaises(ValueError): n.source_guard(proof)

    def test_tcl_full_session_in_proc_scope_five_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            (output/'selection.tcl').write_text('set qc_design D\nset qc_vdb V\nset qc_test T\nset qc_python P\nset qc_helper H\nset qc_instances [list [list top.decode [list previous\\[0\\].pc\\[1:0\\]]]]\n')
            script=r'''
set ::qc_test_only 1
set ::env(DVE_COVERAGE_OUTPUT) {__OUTPUT__}
source {__HELPER__}
set opened 0; set stages {}; set events {}
proc gui_open_cov {args} {incr ::opened; if {$::opened != 1} {error duplicate_open}}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_action {args} {}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_get_property {args} {
    set col [lindex $args end]
    switch $col {0 {return Variable} 4 {return Type} 5 {return Coverage} 6 {return Display}}
    if {$col > 6} {error end}
    return ""
}
proc gui_list_get {args} {
    if {[lsearch -exact $args -firstChild] >= 0} {
        if {[lindex $args end] eq "-firstChild"} {return 1}
        return 0
    }
    if {[lsearch -exact $args -nextSibling] >= 0} {return 0}
    if {[lsearch -exact $args -path] >= 0} {return nativepath}
    if {[lsearch -exact $args -meta] >= 0} {return nativemeta}
    set col [lindex $args end-1]
    switch $col {0 {return {previous[0].pc[1:0]}} 4 {return Toggle} 5 {return 53.25} 6 {return 53.25}}
    error badcolumn
}
proc gui_exclusion_file {args} {lappend ::events [lindex $args 0]}
proc gui_exclusion {args} {lappend ::events [lindex $args 0]}
proc gui_cov_excl_review {args} {return 1}
rename exec actual_exec
proc exec {args} {return EL_EXACT}
rename qc_audit actual_audit
proc qc_audit {stage} {lappend ::stages $stage; actual_audit $stage}
qc_session
if {$opened != 1 || $stages ne "before selected reset reloaded final"} {error session_contract}
puts MOCK_FULL_SESSION_PASS
'''.replace('__OUTPUT__',str(output)).replace('__HELPER__',str(n.HERE/'cva6_fixed_fields_native768.tcl'))
            p=subprocess.run(['tclsh'],input=script,text=True,capture_output=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(p.stderr,'')
            self.assertIn('MOCK_FULL_SESSION_PASS',p.stdout)
            self.assertEqual(n.native_rows((output/'native_before_0.tsv').read_text())['previous[0].pc[1:0]']['coverage'],'53.25')


if __name__=='__main__': unittest.main()
