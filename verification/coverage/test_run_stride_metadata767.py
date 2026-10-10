"""Host corruption tests, plus actual Spike fixture tests when STRIDE_PREFLIGHT is set."""
import copy
from dataclasses import replace
import os
from pathlib import Path
import unittest
import run_stride_metadata767 as p


class Host(unittest.TestCase):
    def test_all_patterns_one_address(self):
        for step in p.host.PATTERNS:self.assertEqual(p.host.addresses(0x80001040,1,step),[0x80001040])

    def test_vl2_huge_is_not_claimed_safe(self):
        self.assertNotEqual(p.host.addresses(0x80001040,2,p.host.PATTERNS[0]),[0x80001040,0x80001041])

    def test_source_mutation(self):
        actual=p.host.golden();actual['source']=bytes(128)
        with self.assertRaises(ValueError):p.host.validate(actual)

    def test_tail_mutation(self):
        actual=p.host.golden();v=bytearray(actual['vrf_guarded']);v[16+1024+2]^=1;actual['vrf_guarded']=bytes(v)
        with self.assertRaises(ValueError):p.host.validate(actual)

    def test_recovery_mutation(self):
        actual=p.host.golden();v=bytearray(actual['stored']);v[529]^=1;actual['stored']=bytes(v)
        with self.assertRaises(ValueError):p.host.validate(actual)

    def test_csr_mutation(self):
        actual=p.host.golden();actual['csrs']['vstart']=1
        with self.assertRaises(ValueError):p.host.validate(actual)

    def test_ring_all_start_positions(self):self.assertEqual(len(p.host.ring_proof()),4)

    def test_extra_exception(self):
        with self.assertRaises(ValueError):p.validate_reference([],{'trap_fail':1},'exception trap_illegal_instruction')

    def test_unknown_vector_gate(self):
        with self.assertRaises(ValueError):p.vector_gate({'status':'PASS','skipped_unknown_bytes':1},[])

    def test_pin_drift(self):
        with self.assertRaises(ValueError):p.life.check({str(Path(p.__file__)):'0'*64})

    def test_timeout_bound(self):
        self.assertEqual(p.runner.BUDGET,600)


@unittest.skipUnless(os.environ.get('STRIDE_PREFLIGHT'),'Actual fixture requires STRIDE_PREFLIGHT')
class Actual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(os.environ['STRIDE_PREFLIGHT']);cls.trace=(cls.out/'spike.trace').read_text()
        cls.symbols={n:p.shared._elf_symbol(cls.out/'input.elf',p.resources.LLVM/'llvm-readelf',n) for n in p.SYMBOLS}
        cls.commits=p.shared.parse_spike_commits(cls.out/'spike.trace')

    def test_full_reference(self):
        result=p.validate_reference(self.commits,self.symbols,self.trace)
        self.assertEqual(result['checks'],605);self.assertTrue(result['VL1_only_base'])
        self.assertEqual(result['strided_loads'],16);self.assertEqual(result['strided_stores'],16)

    def mutate(self,field,value):
        c=list(self.commits)
        index=next(i for i,x in enumerate(c) if x.instruction&127==7 and (x.instruction>>26)&3==2)
        c[index]=replace(c[index],**{field:value})
        with self.assertRaises(ValueError):p.validate_reference(c,self.symbols,self.trace)

    def test_wrong_vl(self):self.mutate('vector_vl',2)
    def test_wrong_vstart(self):self.mutate('vector_vstart',1)
    def test_extra_address(self):self.mutate('memory_accesses',((self.symbols['source_guard']+64,None),(0x10,None)))
    def test_wrong_address(self):self.mutate('memory_accesses',((self.symbols['source_guard']+65,None),))
    def test_missing_load(self):self.mutate('memory_accesses',())
    def test_elf_fit(self):self.assertTrue(p.fit(self.out/'input.elf'))
    def test_wrong_scope(self):
        symbols=dict(self.symbols,source_guard=self.symbols['source_guard']+8)
        with self.assertRaises(ValueError):p.validate_reference(self.commits,symbols,self.trace)
    def test_exception(self):
        with self.assertRaises(ValueError):p.validate_reference(self.commits,self.symbols,self.trace+'\nexception trap_illegal_instruction\n')


if __name__=='__main__':unittest.main()
