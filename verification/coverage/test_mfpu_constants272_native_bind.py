import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import mfpu_constants272_native_bind as b


def node(name,kind='vectornode',port='0',left='63',right='0',**extra):
    n=dict(name=name,kind=kind,type='1',portnode=port,excluded='0')
    if kind=='vectornode':n.update(left=left,right=right)
    return dict(n,**extra)


def text(rows):
    stream=io.StringIO();writer=csv.writer(stream,delimiter='\t',lineterminator='\n')
    writer.writerow(['handle','path','meta','name','type','coverage','display'])
    for index,(name,kind) in enumerate(rows):
        writer.writerow([str(index+1),name,name,name,kind,'0.00%',''])
    return stream.getvalue()


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.target=node('fmt_outputs[3].result')
        self.array=node('operands_i',kind='arrays',port='2',packedrange='2 0 63 0 ',unpackedrange='')
        self.port=node('ready_i',port='2',left='0',right='0')
        self.i=dict(scope='root.gen_lane[0].i_opgroup',design_module_checksum='123',toggle_checksum='456',
            typed_objects=[self.target,self.array,self.port],targets=[dict(name=self.target['name'],
            attributes=self.target,constant_hex='0xffffffffffffffff')])
        self.rows=[('fmt_outputs[3].result[63:0]','register'),('operands_i[2:0][63:0]','port'),('ready_i','port')]

    def test_actual_target_label_bound_from_row_with_array_dims_and_width1_port(self):
        result=b.bind_inventory(self.i,text(self.rows))
        self.assertEqual(result['signals'][0]['native_label'],self.rows[0][0])
        self.assertEqual(result['signals'][0]['native_meta'],self.rows[0][0])
        self.assertEqual(len(result['signals'][0]['bits']),64)
        self.assertEqual(result['array_bindings']['operands_i'],[self.rows[1][0]])

    def test_full_indexed_array_representation_not_flattened(self):
        rows=[self.rows[0],self.rows[2]]+[(f'operands_i[{i}][63:0]','port') for i in range(3)]
        result=b.bind_inventory(self.i,text(rows))
        self.assertEqual(len(result['array_bindings']['operands_i']),3)
        with self.assertRaises(ValueError):b.bind_inventory(self.i,text(rows[:-1]))
        bare=[self.rows[0],self.rows[2]]+[(f'operands_i[{i}]','port') for i in range(3)]
        with self.assertRaises(ValueError):b.bind_inventory(self.i,text(bare))
        with self.assertRaises(ValueError):b.bind_inventory(self.i,text(self.rows+[('operands_i[0][0]','port')]))

    def test_missing_unknown_wrong_direction_dimension_and_port_rejected(self):
        variants=[self.rows[:-1],self.rows+[('FOREIGN','register')],
                  [self.rows[0],('operands_i[63:0][2:0]','port'),self.rows[2]],
                  [('fmt_outputs[3].result[0:63]','register'),*self.rows[1:]],
                  [(self.rows[0][0],'port'),*self.rows[1:]],
                  [self.rows[0],self.rows[1],('ready_i','register')]]
        for rows in variants:
            with self.subTest(rows=rows),self.assertRaises(ValueError):b.bind_inventory(self.i,text(rows))

    def test_duplicate_scalar_alias_and_target_control_promotion_rejected(self):
        with self.assertRaises(ValueError):b.bind_inventory(self.i,text(self.rows+[('ready_i[0:0]','port')]))
        bad=copy.deepcopy(self.i);bad['targets'][0]['attributes']['portnode']='3'
        with self.assertRaises(ValueError):b.bind_inventory(bad,text(self.rows))
        with self.assertRaises(ValueError):b.bind_inventory(self.i,text(self.rows+[self.rows[0]]))

    def test_indexed_array_keeps_all_ordered_dimensions(self):
        array=node('pipe_q',kind='arrays',packedrange='63 0 ',unpackedrange='1 0 2 0 ')
        self.assertEqual(b.dimensions(array),[(1,0),(2,0),(63,0)])
        i=dict(self.i,typed_objects=[array],targets=[])
        rows=[(f'pipe_q[{a}][{c}][63:0]','register') for a in range(2) for c in range(3)]
        self.assertEqual(b.bind_inventory(i,text(rows))['actual_row_count'],6)
        with self.assertRaises(ValueError):b.bind_inventory(i,text([('pipe_q[5:0][63:0]','register')]))

    def test_proposed_el_only_exact_bound_both_direction_bits(self):
        bound=b.bind_inventory(self.i,text(self.rows));c=dict(instances=[bound])
        proposed=b.pack.native.primitive.candidate(c)
        values=b.pack.native.parse_el(proposed,c)
        self.assertEqual(len(values),128)
        self.assertEqual({v[-1] for v in values},{'0to1','1to0'})
        with self.assertRaises(ValueError):b.pack.native.parse_el(proposed.replace('fmt_outputs[3].result','operands_i'),c)
        with self.assertRaises(ValueError):b.pack.native.parse_el(proposed.replace('0to1','1to0'),c)

    def test_run_requires_explicit_review_before_any_check_or_spawn(self):
        with patch.object(b,'check',side_effect=AssertionError('must not check')):
            with self.assertRaises(ValueError):b.run(Path('/unused'),'1'*64,None)
            with self.assertRaises(ValueError):b.run(Path('/unused'),'1'*64,'0'*64)

    def test_real_source_contract_compiled44_and_full744_children(self):
        s=b.life.read_bound(b.source.CONFIG,b.SOURCE_SHA);b.source.contract(s)
        instances,_=b.compiled_instances(s)
        self.assertEqual(len(instances),788)
        self.assertEqual(sum(len(i['targets']) for i in instances),272)
        self.assertEqual(sum(i['protected_child'] for i in instances),744)
        self.assertEqual(sum(n['kind']=='arrays' for i in instances[:44] for n in i['typed_objects']),64)
        self.assertTrue(all(i['typed_objects'] for i in instances))

    def test_real_prepare_dependency_api_and_transitive_library_pins(self):
        s=b.life.read_bound(b.source.CONFIG,b.SOURCE_SHA)
        pins=b.dependencies(s)
        for p in (b.ROOT_LIBRARY,b.WALK_LIBRARY,b.TCL,b.source.CONFIG,b.TEMPLATE):
            self.assertEqual(pins[str(p)],b.life.digest(p))
        bad=copy.deepcopy(s);bad['pins'][str(b.TCL)]='0'*64
        with self.assertRaises(ValueError):b.dependencies(bad)

    def test_real_generated_tcl_full_entry_source_and_bracketed_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);scope='root.gen_lane[0].gen_operation_groups[3].i_opgroup'
            (out/'selection.tcl').write_text('set mfb_design design\nset mfb_vdb vdb\nset mfb_test sample\nset mfb_scopes [list {'+scope+'}]\n')
            script='''
set mfb_test_only 1
source {%s}
set ::env(DVE_COVERAGE_OUTPUT) {%s}
set ::token {}
set ::writes {}
proc gui_open_cov {args} {}
proc p740_root {} {}
proc p740_save {name} {set f [open [file join $::env(DVE_COVERAGE_OUTPUT) $name] w];close $f}
proc gui_list_get_selected {args} {if {$::token eq ""} {return {}};return [list [list $::token]]}
proc gui_list_select {args} {if {[lindex $args 2] eq "-unselect"} {set ::token {}} else {set ::token [lindex [lindex $args 3] 0]}}
proc gui_list_action {args} {if {[lindex $args end] ne $::token} {error "scope token differs"}}
proc gui_covdetail_query {args} {return Toggle}
proc gui_list_expand {args} {}
proc gui_process_events {args} {}
proc gui_list_get_property {args} {set i [lindex $args end];if {$i>=4} {error done};return [lindex {Variable Type Coverage Display} $i]}
proc gui_list_get {args} {
    set mode [lindex $args 2]
    if {$mode eq "-firstChild"} {if {[llength $args]==3} {return Item1};return 0}
    if {$mode eq "-nextSibling"} {return 0}
    if {$mode eq "-path" || $mode eq "-meta"} {return {fmt_outputs[3].result[63:0]}}
    if {$mode eq "-text"} {return [lindex [list {fmt_outputs[3].result[63:0]} register 0.00%% {}] [lindex $args 3]]}
    error "Unexpected native getter"
}
proc gui_exclude_items {args} {error "No exclusion authorized"}
proc gui_exclusion {args} {error "No reset/recalculate authorized"}
mfb_session
puts MOCK_READONLY_DONE
'''%(b.TCL,out)
            result=subprocess.run(['tclsh'],input=script,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(result.stderr,result.stderr)
            self.assertIn('MOCK_READONLY_DONE',result.stdout)
            self.assertIn(scope,(out/'scopes.tsv').read_text())
            self.assertIn('fmt_outputs[3].result[63:0]',(out/'native_before_0.tsv').read_text())
            self.assertEqual((out/'initial-empty.el').read_bytes(),b'')
            self.assertEqual((out/'final-empty.el').read_bytes(),b'')


if __name__=='__main__':unittest.main()
