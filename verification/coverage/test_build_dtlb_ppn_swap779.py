import unittest
from types import SimpleNamespace as Row
from unittest.mock import patch
import build_dtlb_ppn_swap779 as m


class PpnSwap(unittest.TestCase):
    def test_legal_distinct_pages_complement(self):
        for phase in range(3):
            pages = [m.pa(m.page(phase, i)) for i in range(16)]
            self.assertEqual(len(set(pages)), 16)
            self.assertTrue(all(0x80080000 <= p <= 0x8017f000 and p % 4096 == 0 for p in pages))
        for i in range(16):
            self.assertEqual(((m.pa(m.page(0,i)) >> 12) ^ (m.pa(m.page(1,i)) >> 12)) & 255, 255)
            self.assertEqual(m.page(0,i), m.page(2,i))

    def test_model_complete_not_native_claim(self):
        p = m.mapping_proof()
        self.assertFalse(p['runtime_entry_coverage_proven'])
        for phase in p['plru_entry_order']: self.assertEqual(sorted(phase), list(range(16)))

    def test_unique_page_content(self):
        self.assertEqual(len({tuple(m.word(17*i,j) for j in range(512)) for i in range(16)}), 16)
        for i in range(16):
            self.assertEqual(m.word(17*i, 0), m.shared.GUARD)
            self.assertEqual(m.word(17*i, 511), m.shared.GUARD)
            self.assertEqual(m.word(17*i, 1), m.gold(17*i))

    def test_invalid_inputs(self):
        for fn, args in ((m.page,(True,0)), (m.page,(0,16)), (m.pa,(256,)), (m.word,(0,512))):
            with self.assertRaises(ValueError): fn(*args)

    def fixture(self):
        s = {n:0x80003000+0x1000*i for i,n in enumerate(m.SYMBOLS)}
        s['ppm_first_load'], s['ppm_second_load'] = 0x80002204, 0x80002208
        rows = []
        def row(pc=0, memory=(), gpr=None, csr=None, insn=0):
            return Row(pc=pc, instruction=insn, memory_accesses=tuple(memory),
                       gpr_writes=gpr or {}, csr_writes=csr or {}, vector_writes={}, fpr_writes={})
        def store(a,v): rows.append(row(memory=((a,v),)))
        for a,v in ((s['g75_result'],8297), (s['g75_result']+4,0), (s['num_failed'],0),
                    (s['tohost'],1)): store(a,v)
        original=0x6600; setting=(original & ~0x21888)|0x20800
        satp=(8<<60)|(s['ppm_root']>>12)
        for i,v in enumerate([original,0]+[satp]*3+[original]*3+[0]): store(s['ppm_csr']+8*i,v)
        for name in ('ppm_root','ppm_mid','ppm_leaf'):
            for i in range(512): store(s[name]+8*i,0)
        store(s['ppm_root']+16,m.pte(0x80000000,0xcf))
        for i in range(16):
            v=m.shared.vpn(0,i)
            store(s['ppm_root']+8*(v>>18),m.pte(s['ppm_mid'],1))
            store(s['ppm_mid']+8*((v>>9)&511),m.pte(s['ppm_leaf'],1))
            for j in range(512): store(m.pa(17*i)+8*j,m.word(17*i,j))
        for p in range(3):
            rows.append(row(pc=0x80002400,csr={0x180:satp}))
            for i in range(16):
                store(s['ppm_leaf']+8*(m.shared.vpn(0,i)&511),m.pte(m.pa(m.page(p,i)),0xc7))
                rows.append(row(pc=0x80002200,csr={0x300:setting}))
                for b in range(2):
                    pc=s['ppm_first_load' if b==0 else 'ppm_second_load']; value=m.gold(m.page(p,i))
                    rows.append(row(pc=pc,memory=((m.address(i),None),),gpr={10:value},insn=0x3003))
                    # These result stores occur only after restoration in the real ELF.
                rows.append(row(pc=0x80002210,csr={0x300:original}))
                for b in range(2): store(s['ppm_observed']+8*(p*32+i*2+b),m.gold(m.page(p,i)))
        rows.append(row(pc=0x80002404,csr={0x180:0}))
        for i in range(16):
            for j in range(512):
                value=m.word(17*i,j)
                rows.append(row(memory=((m.pa(17*i)+8*j,None),),gpr={10:value},insn=0x3003))
        for i in range(3): store(s['g75_trap']+8*i,0)
        return rows,s

    def check(self, mutate=None):
        rows,s=self.fixture()
        if mutate: mutate(rows,s)
        with patch.object(m.shared.architecture,'reference_counts',return_value={'complete':True}):
            return m.validate(rows,s)

    def reject(self, mutate):
        with self.assertRaises(ValueError): self.check(mutate)

    def test_full_positive(self): self.assertEqual(self.check()['physical_data_bytes'],65536)

    def test_wrong_translated_data(self):
        self.reject(lambda r,s: setattr(next(c for c in r if c.pc==s['ppm_first_load']),'gpr_writes',{10:0}))

    def test_missing_target_load(self):
        self.reject(lambda r,s: r.pop(next(i for i,c in enumerate(r) if c.pc==s['ppm_first_load'])))

    def test_wrong_mapping_phase(self):
        def mutate(r,s):
            a=s['ppm_leaf']+8*(m.shared.vpn(0,0)&511)
            c=[c for c in r if any(p==a and v is not None for p,v in c.memory_accesses)][2]
            c.memory_accesses=((a,m.pte(m.pa(0),0xc7)),)
        self.reject(mutate)

    def test_interior_page_word_wrong(self):
        self.reject(lambda r,s:setattr(next(c for c in r if (m.pa(0)+8*100,None) in c.memory_accesses),
                                     'gpr_writes',{10:0}))

    def test_extra_page_store(self):
        def mutate(r,s):
            c=Row(pc=0,instruction=0,memory_accesses=((m.pa(0)+8,m.gold(0)),),
                  gpr_writes={},csr_writes={},vector_writes={},fpr_writes={})
            r.append(c)
        self.reject(mutate)

    def test_asid_changed(self):
        self.reject(lambda r,s:setattr(next(c for c in r if 0x180 in c.csr_writes),
                                      'csr_writes',{0x180:(8<<60)|(1<<44)|(s['ppm_root']>>12)}))

    def test_extra_mprv_memory(self):
        def mutate(r,s):
            c=next(c for c in r if c.pc==s['ppm_first_load']); c.pc=0x80002300
        self.reject(mutate)

    def test_source_closure(self):
        names=('core/cva6_mmu/cva6_tlb.sv','core/cva6_mmu/cva6_mmu.sv',
               'core/include/cv64a6_imafdcv_sv39_config_pkg.sv')
        texts={p.split('/')[-1]:(m.ROOT/'hardware/deps/cva6'/p).read_text() for p in names}
        self.assertEqual(m.shared.source_contract(texts)['entries'],16)
        texts['cva6_tlb.sv']=texts['cva6_tlb.sv'].replace('content_n[i].pte = update_i.content;',
                                                                    "content_n[i].pte = '0;")
        with self.assertRaises(ValueError): m.shared.source_contract(texts)

    def test_probe_readonly_complete(self):
        text=(m.ROOT/'verification/coverage/dtlb_ppn_swap_probe.tcl').read_text()
        for token in ('update_i','replace_en','lu_hit','lu_access_i','content_q','tags_q','flush_i'):
            self.assertIn(token,text)
        self.assertNotIn('force ',text)


if __name__ == '__main__': unittest.main()
