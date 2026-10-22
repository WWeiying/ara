import unittest
from coverage_gate import SetupLedger, word_read
from completion_cache import CompletionCache

CASE = dict(seed=2, start=1, bytes=1, registers=8)


def input_word(offset):
    return sum((((offset+j)*37+CASE['seed']*71+3)&255) << (8*j) for j in range(8))


def setup(gate, omit=None):
    for i in range(0,1024,8):
        if i != omit:
            gate.store(0x1000+i,8,input_word(i),CASE)
    for i in range(0,1088,8):
        gate.store(0x2000+i,8,0x5b5b5b5b5b5b5b5b,CASE)


def output_word(offset):
    return sum((((i-32)*37+145)&255 if 33<=i<1056 else 91) << (8*j)
               for j,i in enumerate(range(offset,offset+8)))


class GateTests(unittest.TestCase):
    def test_fresh_positive_next_call(self):
        g=SetupLedger(0x1000,0x2000)
        setup(g);g.enter();setup(g);g.enter()
        self.assertEqual((g.calls,g.input_stores,g.output_stores),(2,256,272))

    def test_remove_whole_repeated_initialization(self):
        g=SetupLedger(0x1000,0x2000);setup(g);g.enter()
        with self.assertRaises(ValueError):g.enter()

    def test_missing_input_word_and_last_output(self):
        with self.assertRaises(ValueError):setup(SetupLedger(0x1000,0x2000),omit=16)
        g=SetupLedger(0x1000,0x2000)
        for i in range(0,1024,8):g.store(0x1000+i,8,input_word(i),CASE)
        for i in range(0,1080,8):g.store(0x2000+i,8,0x5b5b5b5b5b5b5b5b,CASE)
        with self.assertRaises(ValueError):g.enter()

    def test_setup_duplicate_width_value_address(self):
        for address,size,value in [(0x1000,1,input_word(0)),(0x1008,8,input_word(8)),
                                   (0x1000,8,input_word(0)^1),(0x2000,8,0x5b5b5b5b5b5b5b5b)]:
            with self.assertRaises(ValueError):SetupLedger(0x1000,0x2000).store(address,size,value,CASE)
        g=SetupLedger(0x1000,0x2000);g.store(0x1000,8,input_word(0),CASE)
        with self.assertRaises(ValueError):g.store(0x1000,8,input_word(0),CASE)

    def test_complete_word_oracle_and_cache(self):
        active=dict(ordinal=0,tuple=CASE,reads=set(),returned=True,csrs=[1,0],preloads=2,stores=1)
        for i in range(0,1088,8):word_read(active,i,8,output_word(i))
        CompletionCache().finish(active)
        self.assertEqual(len(active['reads']),1088)
        with self.assertRaises(ValueError):word_read(active,0,8,output_word(0))

    def test_oracle_missing_guard_bad_value_and_width(self):
        for offset,size,value in [(8,8,output_word(8)),(0,1,91),(0,8,output_word(0)^1)]:
            with self.assertRaises(ValueError):word_read(dict(tuple=CASE,reads=set()),offset,size,value)
        active=dict(ordinal=0,tuple=CASE,reads=set(),returned=True,csrs=[1,0],preloads=2,stores=1)
        for i in range(0,1080,8):word_read(active,i,8,output_word(i))
        with self.assertRaises(ValueError):CompletionCache().finish(active)


if __name__=='__main__':unittest.main(verbosity=2)
