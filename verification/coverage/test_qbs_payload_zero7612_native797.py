import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import qbs_payload_zero7612_native797 as n


def tsv(header, rows):
    out = io.StringIO()
    writer = csv.writer(out, delimiter='\t', lineterminator='\n')
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


class BinderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = n.read_bound(n.PACKET, n.PACKET_SHA)
        cls.proof = n.evidence()
        cls.instances = cls.proof['instances']

    def bit_fixture(self, stage='before'):
        name = 'gen_write_merge[0].gen_bank_plane[2].gen_bank_row[0].gen_byte_merge[0].hit'
        obj = dict(name=name, width=16, label=name+'[15:0]', selected_bits=[2, 6])
        inst = dict(objects=[obj])
        rows = [[name, str(b), '%s[%d]'%(name,b), '%s[%d]'%(name,b), '%s[%d]'%(name,b),
                 '0.00%' if b in obj['selected_bits'] else '100.00%',
                 str(int(b in obj['selected_bits'] and stage in ('applied', 'reloaded'))),
                 str(int(b in obj['selected_bits'] and stage in ('applied', 'reloaded')))] for b in range(16)]
        header = ['signal', 'bit', 'path', 'meta', 'name', 'coverage', '0to1', '1to0']
        return inst, header, rows

    def el_fixture(self):
        lines = []
        for inst in self.instances:
            selected = [o for o in inst['objects'] if o['selected_bits']]
            if not selected:
                continue
            lines += ['CHECKSUM: "%s %s"'%(inst['design_checksum'],inst['toggle_checksum']),
                      'INSTANCE: '+inst['scope'], 'ANNOTATION: "'+n.ANNOTATION+'"']
            lines += ['Toggle %s [%d] "logic %s"'%(o['name'], b, o['label'])
                      for o in selected for b in o['selected_bits']]
        return '\n'.join(lines)+'\n'

    def test_actual_packet_and_raw797_prefix_suffix(self):
        targets, coords = n.target_map(self.packet)
        self.assertEqual(len(coords), 7612)
        self.assertEqual(sum(len(x['bits']) for x in targets.values()), 3806)
        self.assertEqual(self.proof['suffix_receipt']['status'], 'RAW797_SUFFIX_NO_CANDIDATE_COUNTEREXAMPLE')
        self.assertEqual(self.proof['suffix_receipt']['population'], 797)
        self.assertFalse(self.proof['suffix_receipt']['initial_X_counts_as_known_toggle'])

    def test_full_banks_and_descendants_complement(self):
        scopes = {i['scope'] for i in self.instances}
        self.assertTrue(set(n.source.SCOPES) <= scopes)
        self.assertTrue(any('.i_sram' in s for s in scopes))
        self.assertTrue(all(not o['selected_bits'] for i in self.instances if i['scope'] != n.source.SCOPES[1]
                            for o in i['objects']))
        self.assertEqual(sum(len(o['selected_bits']) for i in self.instances for o in i['objects']),3806)

    def test_source_group_hold_no_selection(self):
        bad=copy.deepcopy(self.packet); bad['groups'][0]['status']='HOLD'
        with self.assertRaises(ValueError): n.target_map(bad)

    def test_source_duplicate_and_wrong_raw_pair_rejected(self):
        for change in ('duplicate', 'coordinate'):
            bad=copy.deepcopy(self.packet)
            t=next(t for g in bad['groups'] for t in g['targets'] if t['unowned_bits'])
            if change=='duplicate': t['unowned_bits'].append(copy.deepcopy(t['unowned_bits'][0]))
            else: t['unowned_bits'][0]['raw_zero_coordinates'][0]+=1
            with self.assertRaises(ValueError): n.target_map(bad)

    def test_raw797_counterexample_is_fatal_even_when_OR_matches(self):
        suffix={s:dict(r,bits='0x0') for s,r in self.packet['raw796_scopes'].items()}
        scope, c=next(iter(n.target_map(self.packet)[1]))
        suffix[scope]['bits']=hex(1<<(suffix[scope]['width']-1-c))
        published=n.source.native.union(self.packet['raw796_scopes'],suffix)
        with self.assertRaisesRegex(ValueError,'counterexample'): n.suffix_gate(self.packet,suffix,published)

    def test_raw797_EL_owned_source_zero_counterexample_rejected(self):
        suffix={s:dict(r,bits='0x0') for s,r in self.packet['raw796_scopes'].items()}
        t=next(t for g in self.packet['groups'] for t in g['targets'] if t['both_direction_EL_removed_bits'])
        scope=t['scope']; coordinate=t['both_direction_EL_removed_bits'][0]['raw_zero_coordinates'][0]
        suffix[scope]['bits']=hex(1<<(suffix[scope]['width']-1-coordinate))
        published=n.source.native.union(self.packet['raw796_scopes'],suffix)
        with self.assertRaisesRegex(ValueError,'counterexample'): n.suffix_gate(self.packet,suffix,published)

    def test_raw797_wrong_OR_width_checksum_missing_bank(self):
        suffix={s:dict(r,bits='0x0') for s,r in self.packet['raw796_scopes'].items()}
        for what in ('OR','width','checksum','bank'):
            bad=copy.deepcopy(suffix); published=copy.deepcopy(self.packet['raw796_scopes'])
            s=n.source.SCOPES[0]
            if what=='OR': published[s]['bits']='0x0'
            elif what=='width': bad[s]['width']+=1
            elif what=='checksum': bad[s]['checksum']='0'
            else: del bad[s]
            with self.assertRaises(ValueError): n.suffix_gate(self.packet,bad,published)

    def test_complete_native_vector_five_phases(self):
        inst,h,rows=self.bit_fixture()
        before=n.bits_gate(tsv(h,rows),inst,'before')
        for stage in n.STAGES:
            i,h,r=self.bit_fixture(stage)
            n.bits_gate(tsv(h,r),i,stage,None if stage=='before' else before)

    def test_adjacent_native_bit_direction_and_coverage_protected(self):
        inst,h,rows=self.bit_fixture(); before=n.bits_gate(tsv(h,rows),inst,'before')
        for col,value in ((6,'1'),(7,'1'),(5,'0.00%')):
            _,_,bad=self.bit_fixture('applied'); bad[3][col]=value
            with self.assertRaises(ValueError): n.bits_gate(tsv(h,bad),inst,'applied',before)

    def test_native_candidate_covered_or_unknown_is_hold(self):
        for coverage in ('50.00%','100.00%','X','--'):
            inst,h,r=self.bit_fixture(); r[2][5]=coverage
            with self.assertRaises(ValueError): n.bits_gate(tsv(h,r),inst,'before')

    def test_native_bit_missing_duplicate_wrong_index_token(self):
        for what in ('missing','duplicate','index','path','meta','direction'):
            inst,h,r=self.bit_fixture()
            if what=='missing': r.pop()
            elif what=='duplicate': r.append(r[0])
            elif what=='index': r[0][1]='16'
            elif what=='path': r[0][2]='foreign'
            elif what=='meta': r[0][3]='foreign'
            else: r[0][6]='X'
            with self.assertRaises(ValueError): n.bits_gate(tsv(h,r),inst,'before')

    def test_full_protected_objects_identity_flag_coverage(self):
        obj=dict(name='clk_i',allowed_labels=['clk_i'],selected_bits=[])
        inst=dict(objects=[obj]); h=['path','meta','name','type','coverage','excluded']
        row=['clk_i','clk_i','clk_i','logic','100.00%','0']
        before=n.objects_gate(tsv(h,[row]),inst,'before')
        for col,value in ((0,'foreign'),(1,'foreign'),(3,'other'),(4,'0.00%'),(5,'1')):
            bad=list(row); bad[col]=value
            with self.assertRaises(ValueError): n.objects_gate(tsv(h,[bad]),inst,'applied',before)
        with self.assertRaises(ValueError): n.objects_gate(tsv(h,[]),inst,'before')

    def test_EL_exact7612_and_grouped_annotations_after_members(self):
        text=self.el_fixture(); c=dict(instances=self.instances)
        self.assertEqual(len(n.el_gate(text,c)),7612)
        rows=text.splitlines(); annotation=rows.pop(2); rows.append(annotation)
        self.assertEqual(n.el_gate('\n'.join(rows)+'\n',c),n.el_gate(text,c))

    def test_EL_no_whole_object_neighbor_duplicate_scope_checksum(self):
        text=self.el_fixture(); c=dict(instances=self.instances)
        toggle=next(s for s in text.splitlines() if s.startswith('Toggle '))
        edits=[text+toggle+'\n', text.replace(toggle,toggle.replace(' [', ' WHOLE [',1),1),
               text.replace('INSTANCE: '+n.source.SCOPES[1],'INSTANCE: '+n.source.SCOPES[0],1),
               text.replace('3657545390','0',1),text.replace(n.ANNOTATION,'wrong'),
               text.replace(toggle,__import__('re').sub(r' \[\d+\] "',' [999] "',toggle),1),
               text.replace(toggle,__import__('re').sub(r' \[\d+\] "',' "',toggle),1)]
        for edit in edits:
            with self.assertRaises(ValueError): n.el_gate(edit,c)

    def test_EL_single_direction_missing_rejected(self):
        text=self.el_fixture(); toggle=next(s for s in text.splitlines() if s.startswith('Toggle '))
        with self.assertRaises(ValueError): n.el_gate(text.replace(toggle,toggle.replace('Toggle ','Toggle 0to1 ',1),1),dict(instances=self.instances))

    def test_no_unsafe_Tcl_atoms_or_MDA_flattening(self):
        for value in ('bad{','bad\\','bad\n','bad\t'):
            with self.assertRaises(ValueError): n.atom(value)
        label,_=n.labels('arrays',dict(name='mem',packedrange='127 0',unpackedrange='0 7'))
        self.assertEqual(label,'mem[0:7][127:0]')

    def test_prepare_invalid_directory_never_popen_or_tool_prepare(self):
        with patch.object(n.tools,'prepare') as prepare,patch.object(subprocess,'Popen') as popen:
            with self.assertRaises(ValueError): n.prepare(Path('/tmp/foreign'))
            prepare.assert_not_called(); popen.assert_not_called()

    def test_Tcl_parse_without_EDA(self):
        script='set ::qb_test_only 1\nsource {%s}\nputs QBS_TCL_HOST_PARSE_ONLY\n'%n.TCL
        result=subprocess.run(['/usr/bin/tclsh'],input=script,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stderr,'')
        self.assertIn('QBS_TCL_HOST_PARSE_ONLY',result.stdout)

    def test_Tcl_native_column_properties_not_hardcoded(self):
        script='''set ::qb_test_only 1
source {%s}
proc gui_list_get_property {args} {
    set index [lindex $args end]
    switch $index {
        0 {return Variable}
        4 {return Type}
        7 {return Coverage}
        9 {return Display}
        default {if {$index > 9} {error END}; return {}}
    }
}
puts [qb_columns]
rename gui_list_get_property {}
proc gui_list_get_property {args} {return Wrong}
if {![catch {qb_columns}]} {error {BAD_COLUMNS_ACCEPTED}}
puts COLUMN_NEGATIVE_HOLD
'''%n.TCL
        result=subprocess.run(['/usr/bin/tclsh'],input=script,text=True,capture_output=True,timeout=10)
        self.assertEqual(result.stderr,'')
        self.assertIn('0 4 7 9',result.stdout)
        self.assertIn('COLUMN_NEGATIVE_HOLD',result.stdout)


if __name__=='__main__': unittest.main()
