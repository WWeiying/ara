"""Actual Spike fixture mutations, no DUT access or simulation."""
import re
import tempfile
import unittest
from pathlib import Path
import preflight_sv39_fault_alternating771 as p

class FaultOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=p.OUT/'sv39-fault-alternating-preflight771-agent-20261007-01'
        cls.text=(cls.pre/'spike.trace').read_text()
        cls.symbols={n:p.build._elf_symbol(cls.pre/'input.elf',p.build.LLVM/'llvm-readelf',n) for n in p.SYMBOLS}
    def check_trace(self,text):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'trace';f.write_text(text)
            return p.validate(f,self.symbols)
    def rejected(self,text):
        self.assertNotEqual(text,self.text)
        with self.assertRaises(ValueError):self.check_trace(text)
    def mutate_store(self,name,offset):
        address=self.symbols[name]+offset
        pattern=r'(\bmem 0x0*%x 0x)([0-9a-f]+)'%address
        matches=list(re.finditer(pattern,self.text));self.assertTrue(matches)
        m=matches[-1]
        return self.text[:m.start()]+m[1]+('%x'%(int(m[2],16)^1))+self.text[m.end():]
    def test_actual(self):
        self.assertEqual(self.check_trace(self.text)['page_faults'],8)
    def test_wrong_cause(self):self.rejected(self.text.replace('exception trap_load_page_fault','exception trap_store_page_fault',1))
    def test_wrong_exception_pc(self):
        text,count=re.subn(r'(exception trap_load_page_fault, epc 0x)([0-9a-f]+)',
          lambda m:m[1]+('%016x'%(int(m[2],16)+4)),self.text,count=1)
        self.assertEqual(count,1);self.rejected(text)
    def test_missing_exception(self):
        self.rejected(re.sub(r'^.*exception trap_load_page_fault.*\n','',self.text,count=1,flags=re.M))
    def test_extra_exception(self):self.rejected(self.text+'\nexception trap_load_page_fault, epc 0x80000000\n')
    def test_fault_tval(self):self.rejected(self.mutate_store('fault_records',16))
    def test_vstart(self):self.rejected(self.mutate_store('fault_records',24))
    def test_snapshot_guard(self):self.rejected(self.mutate_store('fault_vrf',0))
    def test_missing_snapshot(self):
        addr=self.symbols['fault_vrf']+16
        line=next(x for x in self.text.splitlines(True) if re.search(r'\bmem 0x0*%x\b'%addr,x)
          and re.search(r'\(0x([0-9a-f]+)\)',x)
          and int(re.search(r'\(0x([0-9a-f]+)\)',x)[1],16)&127==0x27)
        self.rejected(self.text.replace(line,'',1))
    def test_fault_store_no_effect(self):
        pattern=r'(\(0x[0-9a-f]+\).*e64 m1 l1 c8_vstart 0x0+)'
        line=next(x for x in self.text.splitlines(True) if '0x%016x'%self.symbols['fault_store_pc'] in x and ' e64 ' in x)
        self.rejected(self.text.replace(line,line.rstrip()+' mem 0x00000000255555040 0x1\n',1))
    def test_address_shape(self):
        self.assertEqual(p.ADDRESSES[0]^p.ADDRESSES[1],((1<<64)-(1<<12)))
        self.assertEqual(p.ADDRESSES[1]>>39,(1<<25)-1)

if __name__=='__main__':unittest.main()
