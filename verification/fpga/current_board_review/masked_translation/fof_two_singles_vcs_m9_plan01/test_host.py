"""Narrow synthetic entry negatives; no simulation or reference execution."""
import unittest
import successor as s

def setup(n=8):
    q=s.Checker(s.frozen.specification(n))
    q.regs.update({1:0x80000052,2:q.s['__stack_top']})
    q.bss_next=q.s['__bss_end']
    return q

def row(q,i,value=0):
    r={k:'0' for k in s.old.FIELDS}
    r.update(event='retire',order=str(i),cycle=str(i),pc=f'{q.entry_pcs[i]:x}',insn=f'{s.ENTRY[i]:x}')
    frame=q.s['__stack_top']-224
    if i==0:r.update(rd='2',rd_wdata=f'{frame:x}')
    else:r.update(mem_addr=f'{frame+224-8*i:x}',mem_wmask='ff',mem_wdata=f'{0x80000052 if i==1 else value:x}')
    return r

def prefix(q,count):
    for i in range(count):q.row(row(q,i))

class Host(unittest.TestCase):
    def test_actual_scope_and_all_symbol_keys(self):
        for n in (8,64):
            q=setup(n)
            self.assertEqual(q.regs.keys(),{0,1,2})
            self.assertTrue(set(s.symbol_keys())<=set(q.s))
            self.assertEqual(tuple(q.code[p] for p in q.entry_pcs),s.ENTRY)

    def test_first_opaque_actual_values_not_default_zero(self):
        for n in (8,64):
            for value in (0,0x123456789abcdef0):
                q=setup(n)
                for i in range(14):q.row(row(q,i,value))
                self.assertEqual([x['register'] for x in q.opaque_spills],list(s.CALLEE))
                self.assertEqual([x['value'] for x in q.opaque_spills],[value]*12)
                self.assertEqual(q.regs[8],value)
                self.assertIsNone(q.current_entry)

    def test_bad_address_be_rmask_rd_trap_or_instruction(self):
        for field,value in (('mem_addr','800fffd8'),('mem_wmask','0f'),('mem_rmask','ff'),
                            ('rd','8'),('trap','1'),('insn','e9a6'),('pc','800003a4')):
            q=setup();prefix(q,2);r=row(q,2);r[field]=value
            with self.subTest(field=field),self.assertRaises((ValueError,KeyError)):q.row(r)
            self.assertNotIn(8,q.regs)

    def test_missing_store_not_accepted_as_capture(self):
        q=setup();prefix(q,2);r=row(q,2);r['mem_wmask']='00';q.row(r)
        self.assertNotIn(8,q.regs)
        self.assertFalse(q.opaque_spills)
        with self.assertRaises(ValueError):q.finish()

    def test_sp_initial_unknown_wrong_or_changed(self):
        for action in ('unknown','wrong'):
            q=setup()
            if action=='unknown':del q.regs[2]
            else:q.regs[2]-=16
            with self.assertRaises(ValueError):q.row(row(q,0))
        q=setup();prefix(q,2);q.regs[2]-=16
        with self.assertRaises(ValueError):q.row(row(q,2))

    def test_frame_allocation_value(self):
        q=setup();r=row(q,0);r['rd_wdata']=f'{q.s["__stack_top"]-208:x}'
        with self.assertRaises(ValueError):q.row(r)

    def test_reorder_skip_duplicate_and_reentry(self):
        q=setup();prefix(q,2)
        with self.assertRaises(ValueError):q.row(row(q,3))
        q=setup();prefix(q,3);r=row(q,2);r['order']='3'
        with self.assertRaises(ValueError):q.row(r)
        q=setup();prefix(q,14);r=row(q,0);r['order']='14'
        with self.assertRaises(ValueError):q.row(r)

    def test_known_callee_mismatch_remains_strict(self):
        q=setup();prefix(q,2);q.regs[8]=7
        with self.assertRaises(ValueError):q.row(row(q,2,0))

    def test_unknown_business_store_and_unknown_address_rejected(self):
        q=setup();pc=q.s['fx_younger_store'];insn=q.code[pc]
        r=row(q,2);r.update(pc=f'{pc:x}',insn=f'{insn:x}',mem_addr=f'{q.s["fx_marker"]:x}')
        q.regs[5]=q.s['fx_marker']
        self.assertNotIn(6,q.regs)
        with self.assertRaises(ValueError):q.scalar(r,pc,insn,False)
        del q.regs[5]
        with self.assertRaises(ValueError):q.scalar(r,pc,insn,False)

    def test_unknown_spill_outside_entry_rejected(self):
        q=setup();prefix(q,14);del q.regs[8]
        r=row(q,2)
        with self.assertRaises(ValueError):q.scalar(r,q.entry_pcs[2],s.ENTRY[2],False)

    def test_original_business_error_still_rejected(self):
        q=setup();pc=q.s['fx_younger_store'];insn=q.code[pc]
        q.regs.update({5:q.s['fx_errors'],6:1})
        r=row(q,2);r.update(pc=f'{pc:x}',insn=f'{insn:x}',mem_addr=f'{q.s["fx_errors"]:x}',mem_wdata='1')
        with self.assertRaises(ValueError):q.scalar(r,pc,insn,False)

    def test_actual_spec_and_elf_identity_not_optional(self):
        spec=s.frozen.specification(8);spec['code'][str(spec['symbols']['main'])]=0x7111
        with self.assertRaises(ValueError):s.Checker(spec)

if __name__=='__main__':unittest.main(verbosity=2)
