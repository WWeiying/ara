"""Reuse mature isolated tests and add masked/record/capacity discriminators."""
import unittest
from test_mature import Tests
from checker import parse_line,MASK


class MaskedTests(Tests):
    def test_alloff_spurious_NV_actual_flag_read(self):
        for ordinal,flags in ((38,16),(39,17)):
            c=self.check(ordinal);c.step=10;c.active={}
            with self.assertRaisesRegex(ValueError,'flag oracle'):
                c.helper(dict(x={6:flags},f={},mem=[]),(0,10))

    def test_inactive_bit_preservation(self):
        c=self.ready(10)
        self.assertEqual(c.current()['vl'],1)
        self.assertEqual(c.current()['mode'],1)
        self.assertEqual(c.current()['flags'],0)
        with self.assertRaisesRegex(ValueError,'allowed'):
            c.oracle(c.a['output'],self.value(c)^256,4)

    def test_record_every_mode_two_sticky(self):
        c=self.check(2);c.record_loads=1
        address=c.a['oracle_records']+8
        c.record_load(address,c.memory[address]+sum(c.memory[address+i]<<(8*i) for i in range(1,8)),8)
        self.assertEqual(c.record_index,1)
        c=self.check(1)
        with self.assertRaisesRegex(ValueError,'phase'):
            c.record_load(c.a['oracle_records'],0,8)

    def capacity(self):
        c=self.check();c.boot=5;c.pre=6;c.cap=0;c.nextpc=c.s['capacity'][0]['pc'];c.regs[1]=0x800000fe
        return c

    def caprow(self,c,i,wrongtype=False):
        site=c.s['capacity'][i]
        r=parse_line(f"core 0: 3 0x{site['pc']:x} (0x{site['insn']})\n")
        if i==0:r['x']={5:MASK}
        elif i==1:r['x']={10:16};r['csr']={'vl':16,'vtype':15 if wrongtype else 14,'vstart':0}
        return r

    def test_capacity_three_actual_code(self):
        c=self.capacity()
        for i in range(3):c.consume(self.caprow(c,i))
        self.assertEqual(c.cap,3)

    def test_capacity_drop_duplicate_wrong_vtype(self):
        c=self.capacity()
        with self.assertRaisesRegex(ValueError,'discontinuity'):c.consume(self.caprow(c,1))
        c=self.capacity();c.consume(self.caprow(c,0))
        with self.assertRaisesRegex(ValueError,'discontinuity'):c.consume(self.caprow(c,0))
        c=self.capacity();c.consume(self.caprow(c,0))
        with self.assertRaisesRegex(ValueError,'vtype14'):c.consume(self.caprow(c,1,True))


if __name__=='__main__':
    # Only the subclass suite: inherited22 tests run once, not twice.
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(MaskedTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
