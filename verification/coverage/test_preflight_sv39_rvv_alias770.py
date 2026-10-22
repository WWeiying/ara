import copy
import os
from pathlib import Path
import unittest
import preflight_sv39_rvv_alias770 as p


class StaticTests(unittest.TestCase):
    def test_canonical_complement(self):
        for phase in range(3):
            a=p.address(phase)
            self.assertEqual(a>>39,((1<<25)-1) if a&(1<<38) else 0)
            self.assertEqual(a&4095,64)
        self.assertEqual(p.address(0)^p.address(1),(1<<64)-(1<<12))

    def test_all_initial_pointers(self):
        self.assertEqual(len(p.ring_proof()),16)

    def test_tail_and_unrelated_registers(self):
        for phase in range(3):
            words=p.vrf_words(phase)
            self.assertEqual(len(words),512)
            self.assertEqual(sum(v!=p.SEED for v in words),16)
            self.assertEqual(words[136],p.SEED)
            self.assertEqual(words[264],p.SEED)

    def test_invalid_phase(self):
        with self.assertRaises(ValueError):p.address(3)


@unittest.skipUnless(os.environ.get('ALIAS_PREFLIGHT'),'Set actual preflight fixture')
class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        cls.directory=Path(os.environ['ALIAS_PREFLIGHT'])
        cls.symbols=json.loads((cls.directory/'symbols.json').read_bytes())
        cls.commits=p.build.parse_spike_commits(cls.directory/'spike.trace')

    def test_complete_actual(self):
        self.assertEqual(p.validate(self.commits,self.symbols)['target_stores'],48)

    def test_missing_pair(self):
        c=[x for x in self.commits if x.pc!=self.symbols['alias_store_site']]
        with self.assertRaises(ValueError):p.validate(c,self.symbols)

    def test_wrong_store_value(self):
        c=copy.deepcopy(self.commits)
        x=next(x for x in c if x.pc==self.symbols['alias_store_site'])
        object.__setattr__(x,'memory_accesses',((x.memory_accesses[0][0],0),)+x.memory_accesses[1:])
        with self.assertRaises(ValueError):p.validate(c,self.symbols)

    def test_wrong_load_tail(self):
        c=copy.deepcopy(self.commits)
        x=next(x for x in c if x.pc==self.symbols['alias_load_site'])
        x.vector_writes[16]^=1<<1023
        with self.assertRaises(ValueError):p.validate(c,self.symbols)

    def test_wrong_alias(self):
        c=copy.deepcopy(self.commits)
        x=next(x for x in c if x.pc==self.symbols['alias_store_site'])
        object.__setattr__(x,'memory_accesses',((x.memory_accesses[0][0]^4096,x.memory_accesses[0][1]),)+x.memory_accesses[1:])
        with self.assertRaises(ValueError):p.validate(c,self.symbols)


if __name__=='__main__':unittest.main()
