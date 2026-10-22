import unittest
from types import SimpleNamespace as Row
import build_tlb_asid_matrix as m


class Matrix(unittest.TestCase):
    def test_canonical_distinct_nonidentity(self):
        for p in range(3):
            values = [m.address(p,i) for i in range(16)]
            self.assertEqual(len(set(values)),16)
            self.assertTrue(all(((v >> 39) == ((1 << 25)-1) if v & (1 << 38) else v >> 39 == 0)
                                and ((v >> 30)&511) != 2 for v in values))

    def test_complement_per_entry(self):
        for i in range(16):
            self.assertEqual(m.vpn(0,i)^m.vpn(1,i),0x7ffffff)
            self.assertEqual(m.vpn(0,i),m.vpn(2,i))

    def test_plru_full_and_stable(self):
        orders = m.plru_order()
        self.assertEqual(orders[0],orders[1]);self.assertEqual(orders[1],orders[2])
        self.assertEqual(sorted(orders[0]),list(range(16)))

    def test_actual_compressed_ld_and_nonzero_offset_reject(self):
        self.assertTrue(m.is_ld_zero(0x611c))
        self.assertTrue(m.is_ld_zero(0x6310))
        self.assertFalse(m.is_ld_zero(0x651c))
        self.assertFalse(m.is_ld_zero(0xe11c))

    def test_positive_full_oracle(self):
        from unittest.mock import patch
        rows,s = self.fixture()
        with patch.object(m.architecture,'reference_counts',return_value={'complete':True}):
            self.assertEqual(m.validate(rows,s),{'complete':True})

    def fixture(self):
        s = {n:0x80000000+i*0x1000 for i,n in enumerate(m.SYMBOLS)}
        rows = []
        def store(a,v):rows.append(Row(pc=0,instruction=0,gpr_writes={},vector_writes={},memory_accesses=[(a,v)]))
        for a,v in ((s['g75_result'],107),(s['g75_result']+4,0),(s['num_failed'],0),(s['tohost'],1)):store(a,v)
        csr = [0x6600,0]+[(8<<60)|((65535 if p != 1 else 0)<<44)|(s['tam_root']>>12) for p in range(3)]+[0x6600]*3+[0]
        for i,v in enumerate(csr):store(s['tam_csr']+8*i,v)
        for i in range(96):
            store(s['tam_observed']+8*i,m.GOLD)
            rows.append(Row(pc=s['tam_first_load' if i%2 == 0 else 'tam_second_load'],instruction=0x3003,
                gpr_writes={1:m.GOLD},vector_writes={},memory_accesses=[(m.address(i//32,(i%32)//2),None)]))
        pte = lambda a,f:((a>>12)<<10)|f
        table = {s['tam_root']+16:pte(0x80000000,0xcf)}
        for p in range(2):
            for i in range(16):
                v=m.vpn(p,i);table[s['tam_root']+8*(v>>18)]=pte(s['tam_mid'],1)
                table[s['tam_mid']+8*((v>>9)&511)]=pte(s['tam_leaf'],1)
        for i in range(16):table[s['tam_leaf']+8*(m.vpn(2,i)&511)]=pte(s['tam_data'],0xc7)
        for name in ('tam_root','tam_mid','tam_leaf'):
            for i in range(512):store(s[name]+8*i,table.get(s[name]+8*i,0))
        for phase in range(3):
            for i in range(16):store(s['tam_leaf']+8*(m.vpn(phase,i)&511),pte(s['tam_data'],0x3c7 if phase == 1 else 0xc7))
        for a in (s['tam_data'],s['tam_data']+16):
            rows.append(Row(pc=0,instruction=0x3003,gpr_writes={1:m.GUARD},vector_writes={},memory_accesses=[(a,None)]))
        return rows,s

    def reject(self,mutate):
        rows,s=self.fixture();mutate(rows,s)
        with self.assertRaises(ValueError):m.validate(rows,s)

    def test_bad_load(self):
        self.reject(lambda rows,s:setattr(next(r for r in rows if r.pc==s['tam_first_load']),'gpr_writes',{1:0}))

    def test_missing_load(self):
        self.reject(lambda rows,s:rows.pop(next(i for i,r in enumerate(rows) if r.pc==s['tam_first_load'])))

    def test_wrong_pte(self):
        self.reject(lambda rows,s:rows.append(Row(pc=0,instruction=0,gpr_writes={},vector_writes={},
                          memory_accesses=[(s['tam_leaf'],1)])))

    def test_guard_write(self):
        self.reject(lambda rows,s:rows.append(Row(pc=0,instruction=0,gpr_writes={},vector_writes={},
                          memory_accesses=[(s['tam_data'],m.GOLD)])))

    def test_csr_not_restored(self):
        self.reject(lambda rows,s:rows.append(Row(pc=0,instruction=0,gpr_writes={},vector_writes={},
                          memory_accesses=[(s['tam_csr']+64,1)])))

    def test_missing_rsw_phase(self):
        def mutate(rows,s):
            rows[:] = [r for r in rows if not any(v is not None and v & 0x3ff == 0x3c7
                       for a,v in r.memory_accesses)]
        self.reject(mutate)

    def test_actual_frozen_source_contract_and_mutation(self):
        names = ('core/cva6_mmu/cva6_tlb.sv','core/cva6_mmu/cva6_mmu.sv',
                 'core/include/cv64a6_imafdcv_sv39_config_pkg.sv')
        texts = {p.split('/')[-1]:(m.ROOT/'hardware/deps/cva6'/p).read_text() for p in names}
        self.assertEqual(m.source_contract(texts)['entries'],16)
        texts['cva6_tlb.sv'] = texts['cva6_tlb.sv'].replace('lu_hit[i] & lu_access_i','lu_hit[i] | lu_access_i')
        with self.assertRaises(ValueError):m.source_contract(texts)


if __name__ == '__main__':unittest.main()
