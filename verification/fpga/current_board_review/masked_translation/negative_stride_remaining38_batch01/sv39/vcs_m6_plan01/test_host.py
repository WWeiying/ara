"""Small artificial checks, not a DUT or architectural reference replay."""
from pathlib import Path
import unittest

import csv_check as c

SOFTWARE = Path(__file__).resolve().parent.parent/'software01'


class Gates(unittest.TestCase):
    def test_all_ten_group_definitions(self):
        groups = [c.Checker(SOFTWARE/f'group{i:02d}') for i in range(10)]
        self.assertEqual([len(x.cases) for x in groups],[4]*9+[2])
        self.assertEqual(sum(len(x.cases) for x in groups),38)
        for x in groups:
            self.assertEqual(x.code[x.s['replay_exit']+14],0xa001)
            self.assertEqual(x.code[x.s['replay_exit']+10],0x00a2b023)
            self.assertEqual(x.code[x.s['fault_0_pc']],0x09c55c07)
            self.assertEqual(x.code[x.s['fault_1_pc']],0x09c55c27)

    def test_incomplete_not_accepted(self):
        for i in range(10):
            with self.assertRaises((ValueError,KeyError)):
                c.Checker(SOFTWARE/f'group{i:02d}').finish()

    def test_unfinished_suffix_is_explicitly_unconstrained(self):
        for i in range(10):
            x = c.Checker(SOFTWARE/f'group{i:02d}')
            for j,t in enumerate(x.cases):
                for phase in range(4):
                    want = c.o.expected(x.s,t,phase,j)
                    mem = {a:17 if v is None else v for a,v in want.items()}
                    g = c.o.geom(t)
                    n = 1+g['fault'] if phase==3 or (phase and not g['fault']) else int(phase>0)
                    for k in range(n):
                        self.put(mem,x.s['mx_records']+96*k+24,0x800)
                    c.o.compare(mem,x.s,t,phase,j)
                    for a,v in want.items():
                        if v is None:
                            mem[a] = 233
                    c.o.compare(mem,x.s,t,phase,j)
                    if phase==3:
                        undefined = {a for a,v in want.items() if v is None}
                        allowed = {x.s['mx_fault']+64+128+2*i+b for i in g['active']
                                   if g['fault'] and not t['store'] and i>=g['start'] for b in (0,1)}
                        self.assertEqual(undefined,allowed)
                        for start,size in [(x.s['mx_pages'],8192),(x.s['mx_result'],512),(x.s['mx_out'],260)]:
                            self.assertTrue(all(want[a] is not None for a in range(start,start+size)))

    @staticmethod
    def put(mem,a,v):
        mem.update({a+i:b for i,b in enumerate(v.to_bytes(8,'little'))})

    def test_defined_prefix_guard_memory_mutation_rejected(self):
        for i in range(10):
            x = c.Checker(SOFTWARE/f'group{i:02d}')
            for j,t in enumerate(x.cases):
                want = c.o.expected(x.s,t,3,j)
                mem = dict(want)
                for k in range(1+int(c.o.geom(t)['fault'])):
                    self.put(mem,x.s['mx_records']+96*k+24,0x800)
                for a in [x.s['mx_out'],x.s['mx_out']+128,x.s['mx_result']+64+128,
                          x.s['mx_pages']+8190,x.s['mx_guard_hi'],x.s['mx_input']+126]:
                    changed = dict(mem)
                    changed[a] ^= 1
                    with self.assertRaises(ValueError):
                        c.o.compare(changed,x.s,t,3,j)

    def test_fault_start_not_hardcoded_five(self):
        starts = set()
        faults = alloff = 0
        for i in range(10):
            for t in c.Checker(SOFTWARE/f'group{i:02d}').cases:
                g = c.o.geom(t)
                starts.add(g['start'])
                faults += g['fault']
                alloff += not g['fault']
        self.assertEqual(starts,{2,5,8})
        self.assertEqual((faults,alloff),(14,24))

    def test_scalar_actual_read_never_filled_from_gold(self):
        x = c.Checker(SOFTWARE/'group00')
        # lhu a0,0(a1): a missing byte is learned only from the actual row.
        x.regs[11] = 0x90000000
        r = dict(mem_addr='90000000',mem_rmask='3',mem_wmask='0',mem_wdata='0',rd='10',rd_wdata='1234')
        x.scalar(r,0x0005d503,0,None)
        self.assertEqual(c.o.readint(x.mem,0x90000000,2),0x1234)
        r['rd_wdata'] = '5678'
        with self.assertRaises(ValueError):
            x.scalar(r,0x0005d503,0,None)

    def test_wrong_be_and_signed_load_rejected(self):
        x = c.Checker(SOFTWARE/'group00')
        x.regs[11] = 0x90000000
        r = dict(mem_addr='90000000',mem_rmask='1',mem_wmask='0',mem_wdata='0',rd='10',rd_wdata='ffff')
        with self.assertRaises(ValueError):
            x.scalar(r,0x0005d503,0,None)
        r['mem_rmask'] = '3'
        with self.assertRaises(ValueError):
            x.scalar(r,0x00059503,0,None)

    def test_extra_helper_internal_is_owned(self):
        x = c.Checker(SOFTWARE/'group00')
        self.put(x.mem,x.s['mx_case'],0)
        wrong = 1-x.cases[0]['store']
        pc = x.helpers[wrong][1]
        r = {k:'0' for k in c.FIELDS}
        r.update(event='retire',pc=f'{pc:x}',insn=f'{x.code[pc]:x}')
        with self.assertRaisesRegex(ValueError,'Wrong helper'):
            x.row(r)

    def test_malformed_and_wrong_pc(self):
        x = c.Checker(SOFTWARE/'group00')
        with self.assertRaises(ValueError):
            x.row({})
        r = {k:'0' for k in c.FIELDS}
        r.update(event='retire',pc=f'{x.s["_start"]:x}',insn='deadbeef')
        with self.assertRaisesRegex(ValueError,'PC/ELF'):
            x.row(r)


if __name__=='__main__':
    unittest.main(verbosity=2)
