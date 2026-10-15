"""Short synthetic checker tests, not reference/DUT evidence."""
import copy
import unittest
from checker import Checker,full_config,parse_line,word,MASK

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.s,cls.g=full_config()
    def check(self,ordinal=0):
        c=Checker(self.s,self.g);c.calls=ordinal;c.pre=6;c.cap=3
        return c
    def ready(self,ordinal=0):
        c=self.check(ordinal);g=c.current();c.record_index=g['record_index'];c.record_loads=g['record_index']+1
        for i,(address,value,width) in enumerate(c.expected_setup(g)):
            if 16<=i<24:
                k=i-16;rec=word(c.memory,c.a['oracle_records']+8*g['record_index'],8)
                row=(rec>>(48 if k%2==0 else 56))&255;addr=c.a['input_periods']+32*row+8*(k//2)
                c.input_load(c.s['input_loads'][k]['pc'],addr,word(c.memory,addr,8),8)
            c.setup_store(c.s['stores'][i]['pc'],address,value,width)
        c.active=dict(read=False,vstart=0,flags=g['flags']);return c
    def value(self,c):
        return 91|(sum(min(v)<<i for i,v in enumerate(c.current()['allowed']))<<8)|(91<<24)
    def test_positive_setup_oracle_all_seed_shapes(self):
        for ordinal in (0,8,48,56*4+40,560+56*4,16*560+56*9+48,17919):
            c=self.ready(ordinal);c.oracle(c.a['output'],self.value(c),4)
            self.assertEqual(c.calls,ordinal+1)
    def test_horizontal_parser(self):
        r=parse_line('core   0: 3 0x80000596 (0xf2038053) f 0 0x0000000000008000\n')
        self.assertEqual(r['f'],{0:0x8000})
        r=parse_line('core   0: 3 0x800001bc (0x00000001) x  9 0x0000000000000001 mem 0x80001000\n')
        self.assertEqual(r['x'],{9:1});self.assertEqual(r['mem'],[(0x80001000,None)])
    def test_parser_unknown_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unparsed'):parse_line('core 0: 3 0x80000000 (0x00000013) mystery 3\n')
    def test_missing_final_store(self):
        c=self.ready();c.fresh=40
        with self.assertRaisesRegex(ValueError,'freshness'):c.oracle(c.a['output'],self.value(c),4)
    def test_missing_input_LD(self):
        c=self.ready();c.input_reads=7
        with self.assertRaisesRegex(ValueError,'freshness'):c.oracle(c.a['output'],self.value(c),4)
    def test_wrong_input_period(self):
        c=self.check();g=c.current();c.fresh=16;c.record_index=0
        with self.assertRaisesRegex(ValueError,'period'):c.input_load(c.s['input_loads'][0]['pc'],c.a['input_periods']+8,0,8)
    def test_wrong_record_order(self):
        c=self.check();address=c.a['oracle_records']+8
        with self.assertRaisesRegex(ValueError,'record address'):c.record_load(address,word(c.memory,address,8),8)
    def test_missing_record_group(self):
        c=self.check(8);address=c.a['oracle_records']+8
        with self.assertRaisesRegex(ValueError,'8960'):c.record_load(address,word(c.memory,address,8),8)
    def test_vl0_error(self):
        c=self.ready()
        with self.assertRaisesRegex(ValueError,'allowed'):c.oracle(c.a['output'],self.value(c)^256,4)
    def test_active_error(self):
        c=self.ready(48)
        with self.assertRaisesRegex(ValueError,'allowed'):c.oracle(c.a['output'],self.value(c)^256,4)
    def test_tail_alternatives_and_rejection(self):
        ordinal=next(i for i,g in enumerate(self.g) if g['vl']>0 and any(k>=g['vl'] and a==[1] for k,a in enumerate(g['allowed'])))
        c=self.ready(ordinal);g=c.current();bit=next(k for k,a in enumerate(g['allowed']) if k>=g['vl'] and a==[1])
        with self.assertRaisesRegex(ValueError,'allowed'):c.oracle(c.a['output'],self.value(c)^(1<<(8+bit)),4)
        c=self.ready(ordinal);value=91|(sum(max(v)<<i for i,v in enumerate(c.current()['allowed']))<<8)|(91<<24)
        c.oracle(c.a['output'],value,4)
    def test_guard_both(self):
        for xor in (1,1<<24,1|(1<<24)):
            c=self.ready()
            with self.assertRaisesRegex(ValueError,'guards'):c.oracle(c.a['output'],self.value(c)^xor,4)
    def test_missing_NV(self):
        c=self.ready(next(i for i,g in enumerate(self.g) if g['flags']&16));c.active['flags']^=16
        with self.assertRaisesRegex(ValueError,'CSR'):c.oracle(c.a['output'],self.value(c),4)
    def test_vstart(self):
        c=self.ready();c.active['vstart']=1
        with self.assertRaisesRegex(ValueError,'CSR'):c.oracle(c.a['output'],self.value(c),4)
    def test_short_output_read(self):
        c=self.ready()
        with self.assertRaisesRegex(ValueError,'LWU'):c.oracle(c.a['output'],self.value(c),2)
    def scalar_case(self,seed):
        ordinal=seed*560+4*56;c=self.check(ordinal);c.step=7;c.active=dict(read=False,vstart=None,flags=None);c.regs[7]=c.current()['b'][0]
        return c
    def test_raw_ft0_all32(self):
        for seed in range(32):
            c=self.scalar_case(seed);g=c.current();c.helper(dict(x={},f={0:g['b'][0]},mem=[]), (4,7))
            self.assertEqual(c.raw_scalar_seeds[seed],1)
    def test_boxing_and_zero_wrong(self):
        for raw in (0,0xffffffffffff8000):
            c=self.scalar_case(1)
            with self.assertRaisesRegex(ValueError,'malformed'):c.helper(dict(x={},f={0:raw},mem=[]),(4,7))
    def test_savedflags_restore(self):
        c=self.check(0);c.step=13;c.active={};c.saved_flags=0;c.regs[30]=16
        with self.assertRaisesRegex(ValueError,'restore'):c.helper(dict(x={},f={},mem=[]),(0,13))
    def test_partialEOF_rejected(self):
        c=self.ready();c.oracle(c.a['output'],self.value(c),4)
        with self.assertRaisesRegex(ValueError,'EOF'):c.finish()
    def test_nonpark_after_exit(self):
        c=self.check();c.boot=5;c.exited=True
        with self.assertRaisesRegex(ValueError,'pure park'):c.consume(parse_line('core 0: 3 0x8000007e (0x0000a001) x1 0x0\n'))
    def test_actual_PC_code_gate(self):
        c=self.check();c.boot=5
        with self.assertRaisesRegex(ValueError,'PC/code'):c.consume(parse_line('core 0: 3 0x80000000 (0x00000013)\n'))
    def test_marker_not_prefix(self):
        c=self.check(265)
        with self.assertRaisesRegex(ValueError,'Full17920'):c.validate_complete()

if __name__=='__main__':unittest.main(verbosity=2)
