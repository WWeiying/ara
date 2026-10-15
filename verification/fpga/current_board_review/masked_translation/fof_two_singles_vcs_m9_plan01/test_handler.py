"""Only new handler-scope negatives; main tests are not rerun."""
import unittest
import successor as base
import successor_handler as h
import test_host as entry

def setup(n=8):
    q=h.Checker(base.frozen.specification(n))
    q.regs.update({1:0x80000052,2:q.s['__stack_top']});q.bss_next=q.s['__bss_end']
    for i in range(14):q.row(entry.row(q,i))
    q.step=11;q.cap=3;q.actions=['checkpoint0','enter_s','helper','younger']
    q.csrs.update({0xc20:8,0xc21:q.cfg['vtype'],8:0})
    q.regs[2]=q.frame_sp-16
    q.regs.update({r:r*12345 for r in (5,6,10,11,12,13,14,15,16,17)})
    for name,value in (('fx_return',q.cfg['returned_vl']),('fx_marker',1)):
        for i,b in enumerate(value.to_bytes(8,'little')):q.mem[q.s[name]+i]=b
    return q

def row(q,pc,**kw):
    r={k:'0' for k in base.old.FIELDS}
    r.update(event='retire',order=str(q.retired),cycle=str(q.last_cycle+1),
             pc=f'{pc:x}',insn=f'{q.code[pc]:x}')
    r.update({k:str(v) for k,v in kw.items()})
    return r

def ecall(q):q.row(row(q,q.s['fx_ecall'],trap=1))

def save_row(q,i):
    frame=q.frame_sp-16-128
    r=row(q,q.trap_pcs[i])
    if i==0:r.update(rd='2',rd_wdata=f'{frame:x}')
    else:
        reg=h.HANDLER_REGS[i-1]
        value=q.regs.get(reg,0x1234567800000000+reg)
        r.update(mem_addr=f'{frame+8*(i-1):x}',mem_wmask='ff',mem_wdata=f'{value:x}')
    return r

def prefix(q,n):
    ecall(q)
    for i in range(n):q.row(save_row(q,i))

def restore_row(q,i):
    reg=h.HANDLER_REGS[i]
    return row(q,q.restore_pcs[i],rd=reg,rd_wdata=f'{q.trap_saved[reg]:x}',
               mem_addr=f'{q.trap_sp+8*i:x}',mem_rmask='ff')

class Handler(unittest.TestCase):
    def test_both_exact_entries_and_full_value_restore(self):
        for n in (8,64):
            q=setup(n);prefix(q,17)
            self.assertEqual(q.handler_opaque,list(h.OPAQUE))
            self.assertEqual(q.trap_saved[7],0x1234567800000007)
            for i in range(16):q.row(restore_row(q,i))
            self.assertEqual(q.handler_restored,list(h.HANDLER_REGS))

    def test_no_ecall_handler_entry(self):
        q=setup()
        with self.assertRaises(ValueError):q.row(save_row(q,0))

    def test_wrong_ecall_trap_or_source_context(self):
        q=setup()
        with self.assertRaises(ValueError):q.row(row(q,q.s['fx_ecall'],trap=0))
        q=setup();q.actions.pop()
        with self.assertRaises(ValueError):ecall(q)
        q=setup();q.csrs[0xc20]=4
        with self.assertRaises(ValueError):ecall(q)

    def test_wrong_handler_address_be_register_trap(self):
        for field,value in (('mem_addr','800ffe90'),('mem_wmask','f'),('mem_rmask','ff'),
                            ('rd','7'),('insn','01c13c23'),('trap','1')):
            q=setup();prefix(q,4);r=save_row(q,4);r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):q.row(r)
            self.assertNotIn(7,q.regs)

    def test_unapproved_unknown_a7_and_known_value_mismatch(self):
        q=setup();del q.regs[17];prefix(q,16)
        with self.assertRaises(ValueError):q.row(save_row(q,16))
        q=setup();prefix(q,1);r=save_row(q,1);r['mem_wdata']='0'
        with self.assertRaises(ValueError):q.row(r)

    def test_first_handler_save_outside_handler_or_body(self):
        q=setup();r=save_row(q,4)
        with self.assertRaises(ValueError):q.scalar(r,q.trap_pcs[4],q.trap_codes[4],False)
        q=setup();prefix(q,17);del q.regs[7]
        with self.assertRaises(ValueError):q.scalar(save_row(q,4),q.trap_pcs[4],q.trap_codes[4],False)

    def test_wrong_sp_or_frame_allocation(self):
        q=setup();ecall(q);q.regs[2]-=16
        with self.assertRaises(ValueError):q.row(save_row(q,0))
        q=setup();ecall(q);r=save_row(q,0);r['rd_wdata']='800ffe90'
        with self.assertRaises(ValueError):q.row(r)

    def test_missing_repeated_handler_and_restore_reorder(self):
        q=setup();prefix(q,4)
        with self.assertRaises(ValueError):q.row(save_row(q,5))
        q=setup();prefix(q,17)
        with self.assertRaises(ValueError):q.row(save_row(q,0))
        q=setup();prefix(q,17)
        with self.assertRaises(ValueError):q.row(restore_row(q,1))

    def test_restore_value_address_be_register(self):
        for field,value in (('rd_wdata','bad'),('mem_addr','800ffe88'),('mem_rmask','0f'),('rd','5')):
            q=setup();prefix(q,17);r=restore_row(q,0);r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):q.row(r)

    def test_missing_actual_main_spill_now_rejected_immediately(self):
        q=h.Checker(base.frozen.specification(8));q.regs.update({1:0x80000052,2:q.s['__stack_top']})
        q.bss_next=q.s['__bss_end']
        q.row(entry.row(q,0));q.row(entry.row(q,1));r=entry.row(q,2);r['mem_wmask']='00'
        with self.assertRaises(ValueError):q.row(r)

if __name__=='__main__':unittest.main(verbosity=2)
