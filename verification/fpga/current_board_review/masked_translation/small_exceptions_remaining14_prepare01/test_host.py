"""Synthetic checker negatives and real generated Host tables; no DUT/reference."""
import copy
import unittest
import prepare as p
import observer as o
import abi_check as abi
import csv_check as core
import source_owners as owners

def row(pc,code,order=0,rd=0,value=0,address=0,wm=0,rm=0,data=0,trap=0):
    r={k:'0' for k in core.FIELDS}
    r.update(cycle=str(order+1),event='retire',order=str(order),pc=f'{pc:x}',insn=f'{code:x}',
             rd=str(rd),rd_wdata=f'{value:x}',mem_addr=f'{address:x}',mem_wmask=f'{wm:x}',mem_rmask=f'{rm:x}',mem_wdata=f'{data:x}',trap=str(trap))
    return r

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs={}
        for sew,sc in o.MEMBERS:
            d=p.HERE/'software01'/p.key(sew,sc)
            cls.specs[sew,sc]=p.read(d/'soc.spec.json')
    def test_exact14(self):
        self.assertEqual(len(self.specs),14)
        self.assertNotIn((8,0),self.specs)
        for sew,sc in self.specs:self.assertIn(sc,(0,1,2,3,5));self.assertNotEqual(sew,64)
    def test_host_all_original_values(self):
        for sew,sc in self.specs:
            d=p.HERE/'software01'/p.key(sew,sc)
            self.assertEqual(o.host_check((d/'host.stdout').read_text(),sew,sc),2836)
    def test_data_mask_pte_guard_mutations(self):
        for (sew,sc),s in self.specs.items():
            for phase in (0,1):
                gold=o.expected(s['symbols'],sew,phase,sc)
                if phase:
                    a=s['symbols']['fx_records']+24
                    for i,b in enumerate((0x800).to_bytes(8,'little')):gold[a+i]=b
                o.compare(gold,s['symbols'],sew,phase,sc)
                for a in (s['symbols']['fx_out'],s['symbols']['fx_out']+9*(sew//8),s['symbols']['fx_out']+129*(sew//8),
                          s['symbols']['fx_mask'],s['symbols']['fx_mask']+15,s['symbols']['fx_pages']+8192-1,
                          s['symbols']['fx_pages']+16384+8,s['symbols']['fx_guard_hi']+63):
                    bad=gold.copy();bad[a]^=1
                    with self.assertRaises(ValueError):o.compare(bad,s['symbols'],sew,phase,sc)
    def test_only_source_sc0_tail_undefined(self):
        for (sew,sc),s in self.specs.items():
            self.assertEqual([i for i in range(130) if o.output_value(sew,1,i,sc) is None],[5,6,7,8] if sc==0 else [])
            self.assertTrue(all(o.output_value(sew,0,i,sc) is not None for i in range(130)))
            if sc!=0:self.assertEqual(o.output_value(sew,1,8,sc),91)
    def test_target_geometry(self):
        for (sew,sc),s in self.specs.items():
            c=o.spec_values(sew,sc)
            self.assertEqual(c['base'],o.VA+4096-(4*(sew//8) if sc<3 else 0))
            self.assertEqual(c['mask'],255 if sc==0 else 15 if sc in (1,2) else 0)
            self.assertEqual(c['returned_vl'],4 if sc==0 else 8)
            self.assertEqual(len(owners.recipe(s)),4)
    def test_wrong_elf_and_profile(self):
        s=copy.deepcopy(self.specs[8,1]);s['elf_sha256']='0'*64
        with self.assertRaises(ValueError):abi.Checker(s)
        s=copy.deepcopy(self.specs[8,1]);s['abi_profile']['main_codes'][1]^=1
        with self.assertRaises(ValueError):abi.Checker(s)
    def test_wrong_target_or_empty_owner(self):
        s=copy.deepcopy(self.specs[8,1]);s['code'][str(s['helper'][3])]^=1<<24
        with self.assertRaises(ValueError):owners.recipe(s)
        with self.assertRaises(ValueError):owners.MemoryOwners(self.specs[8,1]).finish()
    def test_orphan_done_and_deleted_pair(self):
        q=owners.MemoryOwners(self.specs[8,1]);r=row(0,0);r.update(event='uop_done')
        with self.assertRaises(ValueError):q.row(r,{}, {},{})
        q=owners.MemoryOwners(self.specs[8,1]);q.request_count=4;q.retired=[{'cycle':3}]*4
        q.owners=[dict(allocations=[],completions=[],site=n) for n in ('old_vd','mask','target','result')]
        with self.assertRaisesRegex(ValueError,'nonempty'):q.finish()
    def prologue(self,s,bad=None):
        q=abi.Checker(s);q.regs.update({2:s['symbols']['__stack_top'],1:0x80000060});q.bss_next=s['symbols']['__bss_end']
        sp=q.regs[2]-s['abi_profile']['frame_size']
        for i,pc in enumerate(s['abi_profile']['main_pcs']):
            if i==0:r=row(pc,q.code[pc],i,rd=2,value=sp)
            else:
                slot=s['abi_profile']['main_slots'][i-1];reg=slot['register']
                r=row(pc,q.code[pc],i,address=sp+slot['offset'],wm=255,data=q.regs.get(reg,0x12340000+reg))
            if bad and i==bad[0]:r[bad[1]]=bad[2]
            q.row(r)
        return q
    def test_real_main_profiles_nonzero_unknowns(self):
        for s in self.specs.values():
            q=self.prologue(s);self.assertEqual(q.main_opaque,list(abi.CALLEE))
            self.assertEqual(q.regs[8],0x12340008)
    def test_main_wrong_be_addr_order_and_known_value(self):
        for bad in ((2,'mem_wmask','0'),(2,'mem_addr','80000000'),(2,'pc','80000000'),(1,'mem_wdata','dead')):
            with self.assertRaises(ValueError):self.prologue(self.specs[8,1],bad)
    def test_unknown_business_rejected(self):
        q=self.prologue(self.specs[8,1]);q.regs.pop(31,None);q.regs[5]=q.frame_sp
        insn=(31<<20)|(5<<15)|(3<<12)|0x23
        r=row(q.s['check'],insn,address=q.frame_sp,wm=255,data=17)
        with self.assertRaisesRegex(ValueError,'Unknown business'):q.scalar(r,q.s['check'],insn,0)
    def handler(self,s,wrong=None):
        q=self.prologue(s);q.cap=3;q.step=11;q.actions=['checkpoint0','enter_s','helper','younger']
        q.regs[2]=q.frame_sp-16;q.csrs={0xc20:8,0xc21:q.cfg['vtype'],8:0}
        for name,value in (('fx_return',q.cfg['returned_vl']),('fx_marker',1)):
            for i,b in enumerate(value.to_bytes(8,'little')):q.mem[q.s[name]+i]=b
        for r in (1,5,6,10,11,12,13,14,15,16,17):q.regs[r]=0x991000+r
        pc=q.s['fx_ecall'];q.row(row(pc,q.code[pc],q.retired,trap=1))
        sp=q.regs[2]-128
        for i,pc in enumerate(q.abi['handler_pcs']):
            if i==0:r=row(pc,q.code[pc],q.retired,rd=2,value=sp)
            else:
                reg=abi.HANDLER[i-1];r=row(pc,q.code[pc],q.retired,address=sp+8*(i-1),wm=255,data=q.regs.get(reg,0x552000+reg))
            if wrong and i==wrong[0]:r[wrong[1]]=wrong[2]
            q.row(r)
        for i,pc in enumerate(q.abi['restore_pcs']):
            reg=abi.HANDLER[i];r=row(pc,q.code[pc],q.retired,rd=reg,value=q.handler_saved[reg],address=sp+8*i,rm=255)
            q.row(r)
        return q
    def test_real_handler_nonzero_unknowns_and_restores(self):
        for s in self.specs.values():
            q=self.handler(s);self.assertEqual(q.handler_opaque,list(abi.OPAQUE_HANDLER));self.assertEqual(q.handler_restored,list(abi.HANDLER))
    def test_handler_wrong_spill(self):
        for bad in ((4,'mem_wmask','0'),(4,'mem_addr','80000000'),(4,'mem_wdata','10000000000000000'),(1,'mem_wdata','1')):
            with self.assertRaises(ValueError):self.handler(self.specs[8,1],bad)
    def test_handler_without_ecall(self):
        q=self.prologue(self.specs[8,1]);pc=q.s['fx_handler']
        with self.assertRaises(ValueError):q.row(row(pc,q.code[pc],q.retired,rd=2,value=q.frame_sp-128))
    def test_soc_ctrl_without_tohost(self):
        for s in self.specs.values():
            q=abi.Checker(s);self.assertNotIn('tohost',q.s);q.started=True;q.completed=True
            q.regs.update({5:0xd0000000,10:0})
            r=row(s['exit_store'],q.code[s['exit_store']],address=0xd0000000,wm=255)
            q.scalar(r,s['exit_store'],q.code[s['exit_store']],0);self.assertEqual(q.ctrl,[0])
            with self.assertRaises(ValueError):q.scalar(r,s['exit_store'],q.code[s['exit_store']],0)
    def test_soc_nonzero_exit_and_premature_exit(self):
        for value,done in ((1,True),(0,False)):
            s=self.specs[8,1];q=abi.Checker(s);q.started=True;q.completed=done;q.regs.update({5:0xd0000000,10:value})
            r=row(s['exit_store'],q.code[s['exit_store']],address=0xd0000000,wm=255,data=value)
            with self.assertRaises(ValueError):q.scalar(r,s['exit_store'],q.code[s['exit_store']],0)
    def test_diagnostic_keyerror_preserves_type_context(self):
        import diagnostics
        try:raise KeyError(8)
        except KeyError as e:d=diagnostics.context(e,'scalar',dict(row=19,cycle=123,pc='80000398',insn='e9a2'),case='synthetic')
        self.assertEqual(d['error_type'],'KeyError');self.assertEqual(d['message'],'8');self.assertIn('test_diagnostic',d['traceback'])

if __name__=='__main__':unittest.main(verbosity=2)
