import copy
from pathlib import Path
import unittest
import build_btb_target_ring as b


class Source(unittest.TestCase):
    def test_complementary_canonical_targets(self):
        a,c=b.TARGETS[:2]
        self.assertEqual(a^c,((1<<64)-1)^1)
        self.assertEqual(a&4095,0x554);self.assertEqual(c&4095,0xaaa)
        for x in (a,c): self.assertEqual(x>>39,0x1ffffff if x>>38&1 else 0)

    def test_independent_exact_code_page(self):
        p=b.page()
        self.assertEqual(len(p),4096)
        self.assertEqual(int.from_bytes(p[0x550:0x558],'little'),0x0550051300000000)
        self.assertEqual(int.from_bytes(p[0x558:0x560],'little'),0x8067)
        self.assertEqual(int.from_bytes(p[0xaa8:0xab0],'little'),0x80670aa005130000)
        self.assertEqual(p[0:0x554],bytes(0x554))

    def test_nonoverlapping_pte_maps(self):
        s=dict(btb_root=0x80010000,btb_mid=0x80011000,btb_leaf=0x80012000,btb_page=0x80013000)
        r,m,l=b.tables(s)
        self.assertEqual(sum(v!=0 for v in r),3)
        self.assertEqual(sum(v!=0 for v in m),2)
        self.assertEqual(sum(v!=0 for v in l),2)
        self.assertTrue(all(v&0xff==0x4b for v in l if v))

    def test_source_direct_entry_not_dispatch_jalr(self):
        text=b.APP.read_text()
        self.assertIn('jal ra,btb_bank',text)
        self.assertIn('jalr zero,t1,0',text)
        self.assertIn('.2byte 0x0001',text)
        self.assertNotIn('jalr zero,t2',text)

    def test_exact_interval_rejects_multiple_boot_and_terminal(self):
        from types import SimpleNamespace as C
        rows=[C(pc=0x80000000,memory_accesses=()),C(pc=0x80002000,memory_accesses=((0x80001000,1),))]
        self.assertEqual(b.interval(rows),rows)
        with self.assertRaises(ValueError): b.interval(rows+[rows[0]])
        with self.assertRaises(ValueError): b.interval(rows[:-1])

    def test_actual_frozen_source_pins(self):
        book=b.life.read_bound(b.BOOK,b.BOOK_SHA)
        for rel in ('hardware/deps/cva6/core/frontend/btb.sv',
                    'hardware/deps/cva6/core/frontend/frontend.sv',
                    'hardware/deps/cva6/core/branch_unit.sv'):
            p=b.ROOT/rel
            self.assertEqual(b.life.digest(p),book[str(p)])

    def test_actual_c_ld_and_ldsp_destination(self):
        self.assertEqual(b.ld_destination(0x6314),13)
        self.assertEqual(b.ld_destination(0x6082),1)
        self.assertIsNone(b.ld_destination(0x4314))  # C.LW, not a 64-bit readback.
        self.assertIsNone(b.ld_destination(0x6002))

    def test_real_spike_complete_oracle_and_negative_readback(self):
        import dataclasses
        p=b.OUT/'btb-target-ring-preflight777-agent-20261007-02'
        s={n:b.build._elf_symbol(p/'input.elf',b.build.LLVM/'llvm-readelf',n) for n in b.SYMBOLS}
        cs=b.interval(b.build.parse_spike_commits(p/'spike.trace'))
        exceptions=[('trap_supervisor_ecall',s['btb_s_ecall'])]
        result=b.validate(cs,s,exceptions)
        self.assertEqual(result['matched_instructions'],37753)
        for name in ('btb_results','btb_leaf','btb_page','btb_vrf','btb_restored'):
            index=next(i for i,c in enumerate(cs) if (s[name],None) in c.memory_accesses and
                       b.ld_destination(c.instruction) in c.gpr_writes)
            bad=list(cs);c=cs[index];rd=b.ld_destination(c.instruction)
            values=dict(c.gpr_writes);values[rd]^=1
            bad[index]=dataclasses.replace(c,gpr_writes=values)
            with self.subTest(name=name),self.assertRaises(ValueError): b.validate(bad,s,exceptions)


if __name__=='__main__':unittest.main()
