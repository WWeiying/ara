import copy
import json
import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

import prepare_pmp816_global_union as p


class UnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=p.life.read_bound(p.LOCAL/'capture-result.json',p.LOCAL_SHA)
        cls.c=p.life.read_bound(p.LOCAL/'config.json',cls.q['config_seal'])
        cls.add=(p.LOCAL/'second.el').read_text()
        # A host union fixture from generated794 inputs, NOT qualification.
        cls.base=(p.GLOBAL/'combined.el').read_text()

    def test_actual_794_complete_EL_and_PMP_disjoint(self):
        text=p.union_gate(self.base,self.add,self.c)
        before=p.global794.physical(p.stable.semantic(self.base))
        after=p.global794.physical(p.stable.semantic(text))
        self.assertEqual(sum(bin(mask & ~before.get(k,0)).count('1') for k,mask in after.items()),2176)
        self.assertEqual(p.stable.semantic(self.base)[0],p.stable.semantic(text)[0])
        self.assertTrue(text.startswith(self.base.rstrip('\n')+'\n'))

    def test_actual_first_second_equal(self):
        self.assertEqual(p.local.el_gate((p.LOCAL/'first.el').read_text(),self.c),p.local.el_gate(self.add,self.c))

    def test_scalar_range_alias_collision(self):
        i=self.c['instances'][0];s=next(s for s in i['signals'] if s['kind']=='node')
        old='CHECKSUM: "%s %s"\nINSTANCE: %s\nToggle %s "logic %s[0:0]"\n'%(
            i['design_module_checksum'],i['toggle_checksum'],i['scope'],s['name'],s['name'])
        with self.assertRaises(Exception):p.union_gate(self.base+'\n'+old,self.add,self.c)

    def test_duplicate_partial_parent_MDA_and_checksum_collision(self):
        i=self.c['instances'][0];s=i['signals'][0]
        header='CHECKSUM: "%s %s"\nINSTANCE: %s\n'%(i['design_module_checksum'],i['toggle_checksum'],i['scope'])
        for base in (self.base+'\n'+self.add,
                     self.base+'\n'+header+'Toggle pmpcfg_o "logic pmpcfg_o[7:0]"\n',
                     self.base+'\n'+header+'Toggle 0to1 '+s['name']+' "logic '+s['name']+'"\n',
                     self.base+'\n'+header.replace(i['toggle_checksum'],'0')+'Toggle other "logic other"\n'):
            with self.assertRaises(Exception):p.union_gate(base,self.add,self.c)

    def test_unknown_and_whole_toggle_scope_rejected(self):
        i=self.c['instances'][0]
        header='CHECKSUM: "%s %s"\nINSTANCE: %s\n'%(i['design_module_checksum'],i['toggle_checksum'],i['scope'])
        for line in ('Toggle','Toggle unknownsyntax','State bad'):
            with self.assertRaises(Exception):p.union_gate(self.base+'\n'+header+line+'\n',self.add,self.c)

    def test_unknown_addition_and_MDA_rejected(self):
        for bad in (self.add+'Toggle pmpaddr_o "logic [0:0][53:0]pmpaddr_o"\n',
                    self.add.replace('Toggle ','Branch ',1),self.add.replace('"logic ','"net ',1)):
            with self.assertRaises(Exception):p.union_gate(self.base,bad,self.c)

    def test_missing_global_receipt_or_explicit_seal_HOLD(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'fresh'
            with self.assertRaises(Exception):p.prepare(out,None)
            self.assertFalse(out.exists())

    def test_global_flags_fail_closed(self):
        # This model only exercises the gate; no modeled receipt is published.
        c=dict(pins={},schema=p.global794.SCHEMA,hierarchy_roots=[{}]*72,
               input_ledger=['design']+['test%d'%n for n in range(794)],EL_additions=dict(new_direction_count=7686))
        q=dict(status='CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED',population=794,
               config_seal=p.GLOBAL_CONFIG_SHA,
               actual_selected_tests=794,admission_seal=p.global794.BASE_SHA,source_design_native_pins={},
               EL_additions=c['EL_additions'],new_exclusions_added=True,**{k:True for k in p.FLAGS})
        p.global_gate(q,c)
        for field in p.FLAGS:
            bad=dict(q);bad[field]=False
            with self.assertRaises(Exception):p.global_gate(bad,c)
        bad=dict(q);bad['population']=793
        with self.assertRaises(Exception):p.global_gate(bad,c)

    def test_multi_machine_FSM_exact_compiled_records(self):
        records=p.stable.semantic(self.base)[0]
        target='ara_tb.dut.i_ara_soc.i_system.i_ariane.ex_stage_i.lsu_i.gen_mmu.i_cva6_mmu.i_ptw'
        actual=[r for r in records if r[0]==target and r[1]=='4218964517 3345966803']
        self.assertEqual(len(actual),11)
        self.assertTrue(all(p.compiled_fsm_record(r,records) for r in actual))
        for r in actual:
            bad=list(r);bad[3]=bad[3]+' foreign'
            self.assertFalse(p.compiled_fsm_record(tuple(bad),records))
        header=next(r for r in actual if not r[2])
        bad=(*header[:3],header[3].replace('"','"0',1))
        self.assertFalse(p.compiled_fsm_record(bad,records))

    def test_source_zero_coordinate_and_hit_rejected(self):
        proof=p.life.read_bound(p.local.SOURCE,p.local.SOURCE_SHA)
        r=copy.deepcopy(proof['fresh_candidates'][0]);n=r['compiled'];offset=n['serialized_offset']
        root=ET.Element('tgldef');shape=ET.SubElement(root,'tglshape')
        if offset:ET.SubElement(shape,'vectornode',name='prefix',left=str(offset//2-1),right='0')
        attrs={k:v for k,v in n.items() if k not in ('serialized_offset','logical_width','missing_coordinates','missing_slots')}
        ET.SubElement(shape,'node',attrs)
        scope=r['scope'];width=offset+2
        definitions={scope:dict(shape=ET.tostring(root).decode(),module=r['module'])}
        rows={scope:dict(width=width,bits='0',checksum=r['checksum'])};model=dict(fresh_candidates=[r])
        p.zero_gate(model,rows,definitions)
        rows[scope]['bits']='1'
        with self.assertRaises(Exception):p.zero_gate(model,rows,definitions)
        rows[scope]['bits']='0';r['compiled']['serialized_offset']+=2
        with self.assertRaises(Exception):p.zero_gate(model,rows,definitions)


if __name__=='__main__':unittest.main()
