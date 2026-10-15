import json
from pathlib import Path
import re
import unittest
from lifecycle import INIT, READS, INPUT_CODE, Lifecycle, fractional_group
from model import generate

HERE=Path(__file__).resolve().parent

class ReferenceEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=json.loads((HERE/'spike/symbols.json').read_text())
        cls.code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
            (HERE/'spike/program.dis').read_text(),re.M)}
        cls.helpers=json.loads((HERE/'proof.json').read_text())['backends']['spike']['helpers']
        cls.entries=[cls.helpers[f'op_{i}'][0]['pc'] for i in range(25)]
        cls.seeds,cls.rows,cls.masks=generate()
    def state(self):
        s=Lifecycle(self.s,self.code,self.entries,self.rows,self.masks)
        for addr in range(self.s['__bss_start'],self.s['__bss_end'],8):s.store(0x80000046,0x0002b023,addr,8,0)
        s.enter(self.s['main']);s.enter(self.s['arithmetic_main'])
        return s
    def inputs(self,s):
        seed=s.rows[s.calls]['seed']
        while s.input_cursor<184*(seed+1):
            _,pc,key,offset,value=s.input[s.input_cursor]
            s.store(pc,INPUT_CODE[pc],self.s[key]+offset,1,value)
    def mask(self,s):
        row=s.rows[s.calls]
        for i in range(16):s.store(0x800004d2,0xe394,self.s['mask']+8*i,8,int.from_bytes(self.masks[row['mode']][8*i:8*i+8],'little'))
    def fill(self,s,omit=None):
        for i,(pc,insn,width,offset) in enumerate(INIT):
            if i!=omit:s.store(pc,insn,self.s['out']+offset,width,0x5b5b if width==2 else 0x5b5b5b5b5b5b5b5b)
    def begin(self):
        s=self.state();self.inputs(s);self.mask(s);self.fill(s);s.enter(self.entries[0]);return s
    def test_full4095_lifecycle(self):
        s=self.state()
        for row in self.rows:
            self.inputs(s)
            if row['si']==0:self.mask(s)
            self.fill(s);s.enter(self.entries[row['op']])
            for pc,size,offset in READS:s.read(pc,self.s['out']+offset,size)
        s.finish();self.assertEqual(s.output_reads,36855)
    def test_skip_each_output_store(self):
        for omitted in range(9):
            s=self.state();self.inputs(s);self.mask(s)
            with self.subTest(omitted=omitted),self.assertRaises(ValueError):
                self.fill(s,omitted);s.enter(self.entries[0])
    def test_wrong_output_fields(self):
        pc,insn,width,offset=INIT[0];out=self.s['out']+offset
        for args in ((pc+2,insn,out,width,0x5b5b),(pc,insn^1,out,width,0x5b5b),
                     (pc,insn,out+1,width,0x5b5b),(pc,insn,out,8,0x5b5b),(pc,insn,out,width,0)):
            with self.subTest(args=args),self.assertRaises(ValueError):self.state().store(*args)
    def test_missing_seed_even_if_old_bytes_match(self):
        s=self.state();self.mask(s);self.fill(s)
        with self.assertRaises(ValueError):s.enter(self.entries[0])
    def test_wrong_seed_owner_or_value(self):
        for badowner in (False,True):
            s=self.state();s.calls=1 if badowner else 0
            _,pc,key,offset,value=s.input[0]
            with self.assertRaises(ValueError):s.store(pc,INPUT_CODE[pc],self.s[key]+offset,1,value if badowner else value^1)
    def test_missing_mask(self):
        s=self.state();self.inputs(s);self.fill(s)
        with self.assertRaises(ValueError):s.enter(self.entries[0])
    def test_mask_upper_bytes_and_wrong_owner(self):
        s=self.state()
        for i in range(15):s.store(0x800004d2,0xe394,self.s['mask']+i*8,8,int.from_bytes(self.masks[0][i*8:i*8+8],'little'))
        with self.assertRaises(ValueError):s.store(0x800004d2,0xe394,self.s['mask']+120,8,1)
        s=self.begin()
        with self.assertRaises(ValueError):self.mask(s)
    def test_each_missing_read_and_tail_width(self):
        for omitted in range(9):
            s=self.begin()
            with self.subTest(omitted=omitted),self.assertRaises(ValueError):
                for i,(pc,size,offset) in enumerate(READS):
                    if i!=omitted:s.read(pc,self.s['out']+offset,size)
                self.fill(s);s.enter(self.entries[0])
        s=self.begin()
        for pc,size,offset in READS[:-1]:s.read(pc,self.s['out']+offset,size)
        with self.assertRaises(ValueError):s.read(READS[-1][0],self.s['out']+64,8)
    def test_wrong_read_pc_address_and_value_width(self):
        pc,size,offset=READS[0]
        for args in ((pc+2,self.s['out'],size),(pc,self.s['out']+8,size),(pc,self.s['out'],4)):
            with self.subTest(args=args),self.assertRaises(ValueError):self.begin().read(*args)
    def test_fractional_observed64_not_physical128(self):
        for first in (8,16,24):
            self.assertEqual(fractional_group({first:(1<<1023)},first),bytes(64))
            self.assertNotEqual(fractional_group({first:1<<511},first),bytes(64))
            with self.assertRaises(ValueError):fractional_group({},first)
    def test_late_bss_and_short_boot(self):
        s=self.state()
        with self.assertRaises(ValueError):s.store(0x80000046,0x0002b023,self.s['out'],8,0)
        s=Lifecycle(self.s,self.code,self.entries,self.rows,self.masks)
        with self.assertRaises(ValueError):s.enter(self.s['main'])
    def test_literal_code_drift(self):
        code=dict(self.code);code[INIT[0][0]]^=1
        with self.assertRaises(ValueError):Lifecycle(self.s,code,self.entries,self.rows,self.masks)

if __name__=='__main__':unittest.main(verbosity=2)
