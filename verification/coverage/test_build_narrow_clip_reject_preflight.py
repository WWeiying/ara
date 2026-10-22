"""Independent encoding/legality and immutable oracle dimension regressions."""
from dataclasses import replace
import ast
from pathlib import Path
import unittest
import build_narrow_clip_reject_preflight as m


class StaticTests(unittest.TestCase):
    def test_header_independently_encoded(self):m.header_audit()
    def test_exact17_not_covered737_cell(self):
        self.assertEqual(len(m.CASES),17)
        self.assertNotIn(1966,[c['line'] for c in m.CASES])
    def test_single_rejection_reason(self):
        counts={}
        for c in m.CASES:
            reason=m.illegality(int(c['word'],16),c['sew'],int(c['lmul'][1:]))
            self.assertEqual(len(reason),1);counts[reason[0]]=counts.get(reason[0],0)+1
        self.assertEqual(counts,dict(WIDE_SOURCE_ALIGNMENT=12,SOURCE_EMUL16=4,SOURCE_EEW128=1))
    def test_legal_alignment_is_not_illegal(self):
        self.assertEqual(m.illegality(m.encode('vnclip','wi',8),8,1),[])
    def test_legal_width_is_not_illegal(self):
        self.assertEqual(m.illegality(m.encode('vnclipu','wx',8),32,1),[])
    def test_other_register_guard_rejected(self):
        w=m.encode('vnclip','wi',8)
        w=(w&~(31<<7))|(17<<7)
        with self.assertRaises(ValueError):m.illegality(w,8,2)
    def test_masked_wrong_opcode_rejected(self):
        for w in [m.encode('vnclip','wi',8)&~(1<<25),0x13]:
            with self.assertRaises(ValueError):m.illegality(w,8,1)
    def test_expected_recovery_full_register(self):
        self.assertEqual(m.expected_register(16,True)[:4],bytes([0x56,0x63,0x70,0x7d]))
        self.assertEqual(m.expected_register(16,True)[4:],m.expected_register(16)[4:])
        for r in range(32):
            if r!=16:self.assertEqual(m.expected_register(r,True),m.expected_register(r))
    def test_vtype_lmul8(self):self.assertEqual(m.vtype(dict(sew=8,lmul='m8')),3)
    def test_repeated_word_distinct_context(self):
        self.assertEqual(m.CASES[9]['word'],m.CASES[12]['word'])
        self.assertNotEqual(m.vtype(m.CASES[9]),m.vtype(m.CASES[12]))
    def test_original_oracle_globals_unchanged(self):
        cases=m.frozen.CASES;ns=m.oracle_functions()
        self.assertIs(m.frozen.CASES,cases);self.assertEqual(len(m.frozen.CASES),24)
        self.assertEqual(len(ns['CASES']),17)
        self.assertIs(ns['verify_elf'],m.frozen.verify_elf)
    def test_non_matrix_literal_rejected(self):
        tree=ast.parse('def f():\n return 24\n')
        with self.assertRaises(ValueError):m.Constants({(3,24)}).visit(tree)
    def test_dimension_counts(self):self.assertEqual(m.CHECKS,3*32*18+17*21+9)
    def test_privately_inherited_signatures(self):
        symbols={name:0x80010000+i*0x1000 for i,name in enumerate(m.SYMBOLS)}
        symbols['trap_fail']=0x80000100
        def read(name,offset=0,width=8):
            if name=='g75_result':return m.CHECKS if offset==0 else 0
            if name=='num_failed':return 0
            if name=='gnr_traps':return 17
            if name=='gnr_restore':return [symbols['trap_fail']]*2+[0]*2+[0x801ffff0]*2+[0]*6
            if name=='gnr_ledger':
                n,i=divmod(offset//8,12);c=m.CASES[n]
                return [2,symbols['gnr_bad_%02d'%n],int(c['word'],16),4,m.vtype(c),1,5,n+1,0x2222,1,117,0x801ffff0][i]
            if name=='gnr_post':
                n,i=divmod(offset//8,9)
                return [0x1111,0x2222,1,0x801ffff0,1,4,m.vtype(m.CASES[n]),5,117][i]
            if name=='gnr_dump':
                pr,w=divmod(offset//8,18);phase,r=divmod(pr,32)
                if w in (0,17):return 0xa5a5a5a5a5a5a5a5
                return int.from_bytes(m.expected_register(r,phase==2)[(w-1)*8:w*8],'little')
            raise AssertionError(name)
        ns=m.oracle_functions()
        def scalar_read(name,offset=0,width=8):
            result=read(name,offset,width)
            return result[offset//8] if name=='gnr_restore' else result
        ns['signatures'](scalar_read,symbols)
        for name,off in [('gnr_ledger',0),('gnr_post',32),('gnr_dump',8)]:
            def corrupt(n,offset=0,width=8):
                value=scalar_read(n,offset,width)
                return value^1 if n==name and offset==off else value
            with self.subTest(name=name),self.assertRaises(ValueError):ns['signatures'](corrupt,symbols)


if __name__=='__main__':unittest.main()
