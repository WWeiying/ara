import unittest
from pathlib import Path
import build_itlb_ppn_aba as p


class Geometry(unittest.TestCase):
    def test_physical_pages_legal_complement(self):
        self.assertEqual((p.PAGES[0]>>12)^(p.PAGES[1]>>12),511)
        self.assertTrue(all(0x80000000<=a and a+4096<0x801f0000 for a in p.PAGES))

    def test_thunks_not_same_gold(self):
        self.assertNotEqual(p.codeword(0,8),p.codeword(1,8))
        self.assertEqual(p.codeword(0,9)&0xffffffff,0x73)
        self.assertEqual(p.codeword(1,9)&0xffffffff,0x73)

    def test_all16_unique_canonical_pcs(self):
        pcs={p.address(0,e) for e in range(16)}
        self.assertEqual(len(pcs),16)
        for a in pcs:
            self.assertEqual(a>>39,(1<<25)-1 if a&(1<<38) else 0)
        self.assertEqual(pcs,{p.address(2,e) for e in range(16)})

    def test_pte_pages_aba_no_guest_no_global(self):
        syms={'itm_mid':0x80008000,'itm_leaf':0x80009000}
        for phase in range(3):
            root,mid,leaf=p.tables(syms,phase)
            self.assertEqual(sum(bool(x) for x in leaf),16)
            expected=((p.PAGES[phase==1]>>12)<<10)|0x4b
            self.assertEqual(set(x for x in leaf if x),{expected})
            self.assertEqual(expected&0xff,0x4b)

    def test_phase_and_entry_bounds(self):
        for args in [(3,0),(0,16),(-1,0)]:
            with self.assertRaises(ValueError):p.address(*args)

    def test_frozen_source_gate(self):
        proof,pins=p.source_contract()
        self.assertEqual(proof['checksum'],'817233724')
        self.assertGreaterEqual(len(pins),7)

    def test_source_no_64kb_oracle(self):
        text=p.APP.read_text()
        self.assertNotIn('itm_code[16][512]',text)
        self.assertEqual(text.count('sfence.vma zero,zero'),2)
        self.assertIn('ipa_page_b[8]=codeword(1,8)',text)
        self.assertIn('fence.i',text)


if __name__=='__main__':unittest.main()
