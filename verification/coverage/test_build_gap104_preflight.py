from copy import deepcopy
from types import SimpleNamespace
import unittest

import build_gap104_preflight as m


def fixture():
    names = set(m.SYMBOLS)
    symbols = {name:0x90000000+i*0x10000 for i,name in enumerate(sorted(names))}
    symbols['g104_bad_a'],symbols['g104_bad_b']=0x80002200,0x80002204
    words=m.expected_words()
    words.update({('g75_result',0):m.CHECKS,('g75_result',4):0,('num_failed',0):0})
    for phase in range(2):
        ledger=[2,symbols['g104_bad_a' if not phase else 'g104_bad_b'],m.WORDS[phase],1,0,0,0,phase+1]
        words.update({('g104_ledger',phase*80+i*8):v for i,v in enumerate(ledger)})
    words.update({('g104_restore',i*8):v for i,v in enumerate((0x100,0x100,0x200,0x200))})
    commits=[SimpleNamespace(pc=0x80000000,vector_writes={},
        memory_accesses=((symbols[name]+offset,value),)) for (name,offset),value in words.items()]
    for phase in range(2):
        for reg in range(32):
            commits.append(SimpleNamespace(pc=0x80000100+4*reg,memory_accesses=(),
                vector_writes={reg:int.from_bytes(bytes([0x40+reg])*128,'little')}))
    commits.append(SimpleNamespace(pc=0x80000004,vector_writes={},memory_accesses=((symbols['tohost'],1),)))
    trace='\n'.join('exception trap_illegal_instruction, epc %s'%hex(symbols[name])
                    for name in ('g104_bad_a','g104_bad_b'))
    return commits,symbols,trace


class PreflightTests(unittest.TestCase):
    def test_opcodes_independently_decoded(self):
        for phase,word in enumerate(m.WORDS):
            self.assertEqual(m.decode(word),dict(nf=2,mew=0,mop=0,vm=1,rs2=8,rs1=10,width=0,
                                                vd=8,opcode=0x27 if phase else 0x07))
            self.assertNotIn(m.decode(word)['nf']+1,(1,2,4,8))

    def test_full_oracle(self):
        commits,symbols,trace=fixture()
        self.assertEqual(m.validate(commits,symbols,trace)['checks'],1309)

    def test_missing_or_wrong_trap_rejected(self):
        commits,symbols,trace=fixture()
        for bad in (trace.splitlines()[0],trace.replace('illegal_instruction','load_access_fault'),
                    trace+'\n'+trace.splitlines()[0]):
            with self.assertRaises(ValueError):m.validate(commits,symbols,bad)

    def test_illegal_retirement_rejected(self):
        commits,symbols,trace=fixture();commits[0].pc=symbols['g104_bad_b']
        with self.assertRaises(ValueError):m.validate(commits,symbols,trace)

    def test_memory_vrf_guard_csr_recovery_corruption_rejected(self):
        commits,symbols,trace=fixture()
        for name,offset in (('g104_dump',0),('g104_dump',8192-8),('g104_target_dump',512),
                            ('g104_recovery_dump',16),('g104_csr',40),('g104_ledger',80+16)):
            bad=deepcopy(commits);address=symbols[name]+offset
            item=next(c for c in bad if c.memory_accesses and c.memory_accesses[0][0]==address)
            item.memory_accesses=((address,item.memory_accesses[0][1]^1),)
            with self.subTest(name=name),self.assertRaises(ValueError):m.validate(bad,symbols,trace)

    def test_extra_vector_write_rejected(self):
        commits,symbols,trace=fixture()
        commits[-2].vector_writes[31]^=1
        with self.assertRaises(ValueError):m.validate(commits,symbols,trace)

    def test_missing_vector_initialization_rejected(self):
        commits,symbols,trace=fixture();commits[-2].vector_writes={}
        with self.assertRaises(ValueError):m.validate(commits,symbols,trace)

    def test_exact720_target_bindings(self):
        evidence=m.target_evidence()
        self.assertEqual([(t['metric'],t['point']['raw_index']) for t in evidence['targets']],
                         [('branch',390),('branch',336),('line',1263),('line',1346)])
        self.assertTrue(all(not t['hit_before'] for t in evidence['targets']))


if __name__=='__main__':unittest.main()
