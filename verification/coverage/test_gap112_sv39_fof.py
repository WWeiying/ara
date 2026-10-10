"""Host-only contracts; no EDA or simulation launch."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import gap112_sv39_fof as p


def fixture():
    s={n:0x80002400+4*i for i,n in enumerate(p.SYMBOLS)}
    s.update(_start=0x80000000,_end=0x8000e000,tohost=0x80001000,trap_fail=0x80000050,
        sf_pages=0x80008000,sf_guard_lo=0x80007fc0,sf_guard_hi=0x8000c000,
        sf_handler=0x80002100,sf_handler_end=0x80002180,sf_fof=0x80002200,
        sf_read_vl=0x80002204,sf_long_div=0x800021f8,sf_recovery_load=0x80002240,
        sf_ecall=0x80002270)
    a=0x8000c080
    for name,size in p.SIZES.items():
        if name in ('sf_pages','sf_guard_lo','sf_guard_hi'): continue
        s[name]=a;a=(a+size+7)&~7
    dis=[f'{s["sf_fof"]:x}: 0103e407 vle32ff.v',f'{s["sf_long_div"]:x}: 838eec57 vdivu.vx',
         f'{s["sf_recovery_load"]:x}: 0203e607 vle32.v']
    dis += [f'{0x80003000+4*i:x}: 00007057 vsetvl' for i in range(14)]
    return s,'\n'.join(dis)


def commit(pc,word=0x23,access=(),**kw):
    fields=dict(pc=pc,instruction=word,memory_accesses=access,fpr_writes={},vector_writes={},
                vector_sew=None,vector_lmul=None,vector_vstart=None)
    fields.update(kw);return SimpleNamespace(**fields)


def trace_fixture():
    s,_=fixture(); mem=p.expected_memory(s)
    for name in ('sf_before','sf_after'):
        for i in range(15):
            value=s['trap_fail'] if i==2 else 0
            for j in range(8): mem[s[name]+8*i+j]=(value >> (8*j)) & 255
    for i in range(8): mem[s['sf_record']+24+i]=(0x800 >> (8*i)) & 255
    rows=[commit(0x80002500,access=((a,v),)) for a,v in sorted(mem.items())]
    rows.append(commit(s['sf_handler'],0x3023,((s['sf_count'],1),)))
    for i in range(10):
        a=s['sf_record']+8*i;value=int.from_bytes(bytes(mem[a+j] for j in range(8)),'little')
        rows.append(commit(s['sf_handler']+4*(i+1),0x3023,((a,value),)))
    rows += [commit(s['sf_long_div']),commit(s['sf_fof'],0x0103e407,((0x40000ffc,None),),
        vector_sew=32,vector_lmul='m2',vector_vstart=0,vector_writes={8:p.prior.WORD}),
        commit(s['sf_read_vl']),commit(s['sf_recovery_load'],0x0203e607,
            tuple((0x40000040+4*i,None) for i in range(8))),
        commit(0x80000040,0x3023,((s['tohost'],1),))]
    trace='\n'.join(f'core   0: 1 0x{s[n]:016x} (0x00000013)' for n in
        ('sf_long_div','sf_fof','sf_read_vl','sf_recovery_load'))
    trace+=f'\nexception trap_supervisor_ecall, epc 0x{s["sf_ecall"]:016x}\n'
    return rows,s,trace


class Contracts(unittest.TestCase):
    def test_real_pin_merge_api_arity(self):
        tree=ast.parse(Path(p.__file__).read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and
               isinstance(n.func,ast.Attribute) and n.func.attr=='merge_pins']
        self.assertTrue(calls)
        self.assertTrue(all(len(n.args)==2 and not n.keywords for n in calls))
        self.assertEqual(len(p.life.merge_pins({'/a':'1'*64},{'/b':'2'*64})),2)

    def test_linked_exact(self):
        s,d=fixture(); self.assertEqual(p.linked(s,d)['second_leaf'],0)

    def test_reject_page_misalignment(self):
        s,d=fixture();s['sf_pages']+=4
        with self.assertRaises(ValueError): p.linked(s,d)

    def test_reject_outside_ram_elf(self):
        s,d=fixture();s['_end']=0x80200000
        with self.assertRaises(ValueError): p.linked(s,d)

    def test_reject_extra_rvv(self):
        s,d=fixture()
        with self.assertRaises(ValueError): p.linked(s,d+'\n80004000: 00007057 vsetvl')

    def test_reject_bad_fof_opcode(self):
        s,d=fixture()
        with self.assertRaises(ValueError): p.linked(s,d.replace('0103e407','0203e407'))

    def test_full_positive_oracle(self):
        rows,s,t=trace_fixture();self.assertEqual(p.validate(rows,s,t)['checks'],2294)

    def test_reject_wrong_prefix(self):
        rows,s,t=trace_fixture();rows.append(commit(0x80002500,access=((s['sf_prefix']+4,0),)))
        with self.assertRaises(ValueError): p.validate(rows,s,t)

    def test_reject_invalid_page_repair(self):
        rows,s,t=trace_fixture();rows.append(commit(0x80002500,access=((s['sf_pages']+12296,1),)))
        with self.assertRaises(ValueError): p.validate(rows,s,t)

    def test_reject_second_page_successful_read(self):
        rows,s,t=trace_fixture();rows.append(commit(0x80002500,access=((0x40001000,None),)))
        with self.assertRaises(ValueError): p.validate(rows,s,t)

    def test_reject_context_drift(self):
        rows,s,t=trace_fixture();rows.append(commit(0x80002500,access=((s['sf_after'],1),)))
        with self.assertRaises(ValueError): p.validate(rows,s,t)

    def test_reject_additional_trap(self):
        rows,s,t=trace_fixture()
        with self.assertRaises(ValueError): p.validate(rows,s,t+'exception trap_load_page_fault, epc 0x80002200\n')

    def test_reject_fof_active_value_but_allow_unread_tail(self):
        rows,s,t=trace_fixture();c=next(c for c in rows if c.pc==s['sf_fof'])
        c.vector_writes[8] |= (0xabcdef << 32)
        p.validate(rows,s,t)
        c.vector_writes[8] ^= 1
        with self.assertRaises(ValueError): p.validate(rows,s,t)

    def test_reject_outside_ram_store(self):
        rows,s,t=trace_fixture();rows.append(commit(0x80002500,access=((0x80200000,1),)))
        with self.assertRaises(ValueError): p.validate(rows,s,t)

    def test_reject_duplicate_handler(self):
        rows,s,t=trace_fixture();rows.append(commit(s['sf_handler'],0x3023,((s['sf_count'],1),)))
        with self.assertRaises(ValueError): p.validate(rows,s,t)

    def test_namespace_private_budget_no_launch(self):
        before=p.prior.frozen.BUDGET
        with patch.object(p.life,'digest',return_value=p.prior.FROZEN_SHA):
            ns=p.namespace(Path('/tmp/test/preflight.json'),{'elf_sha256':'a'*64},{'command':['mock']})
        self.assertEqual(ns['BUDGET'],180);self.assertEqual(p.prior.frozen.BUDGET,before)
        self.assertEqual(ns['command'](Path('/tmp/out')),['mock'])

    def test_existing_run_rejected_before_preflight_access(self):
        with patch.object(Path,'exists',return_value=True),patch.object(p.life,'read_bound') as read:
            with self.assertRaises(ValueError): p.prepared(p.OUT/'any','unused','a'*64)
            read.assert_not_called()


if __name__=='__main__': unittest.main()
