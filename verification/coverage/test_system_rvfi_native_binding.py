import copy
import csv
from pathlib import Path
import tempfile
import unittest
import system_rvfi_native_binding as m


class ExactNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r=m.life.read_bound(m.original.REVIEW,m.original.REVIEW_SHA)
        cls.bound=m.bindings(cls.r)
        cls.path=m.ORIGIN/'native_before.tsv'
        assert m.life.digest(cls.path)==m.ROWS_SHA

    def test_actual_full1206_before_rows(self):
        self.assertEqual(len(m.parse(self.path,self.bound)),1206)

    def test_exact788_and_full418(self):
        self.assertEqual(sum(p['role']=='target' for p in self.bound),788)
        self.assertEqual(sum(p['role']=='protected' for p in self.bound),418)
        self.assertEqual(sum(p['compiled_kind']=='arrays' for p in self.bound),19)

    def test_alias_requires_original_vector_zero_bounds(self):
        p=next(p for p in self.bound if p['compiled_name'] in m.TARGET_SCALARS)
        for changes in ({'left':'1','right':'1'},{'left':'1'},{}):
            a=dict(p['compiled_attributes'],**changes)
            kind='node' if not changes else 'vectornode'
            with self.assertRaises(ValueError):m.label(kind,a,'target')

    def test_no_general_singleton_heuristic(self):
        self.assertEqual(m.label('vectornode',dict(name='unknown_control',left='0',right='0'),'protected'),
            'unknown_control[0:0]')

    def test_array_exact_dimensions_and_role(self):
        p=next(p for p in self.bound if p['compiled_name']=='rvfi_probes.instr.rs1')
        self.assertEqual(p['observed_label'],'rvfi_probes.instr.rs1[0][63:0]')
        a=dict(p['compiled_attributes'],packedrange='1 0 63 0')
        with self.assertRaises(ValueError):m.label('arrays',a,'protected')
        with self.assertRaises(ValueError):m.label('arrays',p['compiled_attributes'],'target')

    def mutate(self,change,stage='before'):
        with self.path.open() as f:reader=csv.DictReader(f,delimiter='\t');rows=list(reader);fields=reader.fieldnames
        change(rows)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'rows.tsv'
            with path.open('w') as f:w=csv.DictWriter(f,fieldnames=fields,delimiter='\t');w.writeheader();w.writerows(rows)
            with self.assertRaises(ValueError):m.parse(path,self.bound,stage)

    def test_missing_protection_duplicate_foreign_rows(self):
        self.mutate(lambda rows:rows.pop())
        self.mutate(lambda rows:rows.__setitem__(0,dict(rows[1])))
        self.mutate(lambda rows:rows[0].update(path='foreign',meta='foreign',name='foreign'))

    def test_scalar_alias_collision_and_width_mutation(self):
        def add_range(rows):
            p=next(p for p in rows if p['name']=='rvfi_instr[0].valid')
            p.update(path=p['path']+'[0:0]',meta=p['meta']+'[0:0]',name=p['name']+'[0:0]')
        self.mutate(add_range)
        def change_width(rows):
            p=next(p for p in rows if p['name']=='rvfi_probes.instr.tval[63:0]')
            p.update(path='rvfi_probes.instr.tval[62:0]',meta='rvfi_probes.instr.tval[62:0]',name='rvfi_probes.instr.tval[62:0]')
        self.mutate(change_width)

    def test_protected_port_array_control_exclusion_rejected(self):
        for name in ('clk_i','rst_ni','axi_req_o.aw.user','rvfi_probes.instr.wdata[1:0][63:0]'):
            self.mutate(lambda rows:next(p for p in rows if p['name']==name).update(excluded='1'))

    def test_selected_targets_exact_not_count_only(self):
        roles={p['observed_label']:p['role'] for p in self.bound}
        def selected(rows):
            for p in rows:p['excluded']=str(int(roles[p['name']]=='target'))
        with self.path.open() as f:reader=csv.DictReader(f,delimiter='\t');rows=list(reader);fields=reader.fieldnames
        selected(rows)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'rows.tsv'
            with path.open('w') as f:w=csv.DictWriter(f,fieldnames=fields,delimiter='\t');w.writeheader();w.writerows(rows)
            self.assertEqual(len(m.parse(path,self.bound,'selected')),1206)
        def swapped(rows):
            selected(rows)
            next(p for p in rows if roles[p['name']]=='target')['excluded']='0'
            next(p for p in rows if p['name']=='clk_i')['excluded']='1'
        self.mutate(swapped,'selected')

    def test_path_meta_header_identity_not_normalized(self):
        self.mutate(lambda rows:rows[0].update(meta='different'))


if __name__=='__main__':unittest.main()
