import unittest
from pathlib import Path
import build_scalar_misalign789 as m

class SoftwareTests(unittest.TestCase):
    def text(self):
        result=[]
        for i in range(6):
            result+=['core   0: exception trap_'+('load' if i%2==0 else 'store')+'_address_misaligned, epc 0x%x'%(0x80002000+(i%2)*4),
                     'core   0: tval 0x%x'%m.ADDRESSES[i//2]]
        return '\n'.join(result)
    def symbols(self):return dict(mis_ld_pc=0x80002000,mis_sd_pc=0x80002004)
    def test_exact_six(self):self.assertEqual([t['cause'] for t in m.traps(self.text(),self.symbols())],[4,6]*3)
    def test_wrong_cause(self):
        with self.assertRaises(ValueError):m.traps(self.text().replace('load_address_misaligned','load_access_fault',1),self.symbols())
    def test_wrong_epc(self):
        with self.assertRaises(ValueError):m.traps(self.text().replace('0x80002000','0x80002008',1),self.symbols())
    def test_wrong_tval(self):
        with self.assertRaises(ValueError):m.traps(self.text().replace('0x2555555003','0x2555555000',1),self.symbols())
    def test_missing_trap(self):
        with self.assertRaises(ValueError):m.traps('\n'.join(self.text().splitlines()[2:]),self.symbols())
    def test_extra_trap(self):
        with self.assertRaises(ValueError):m.traps(self.text()+'\n'+self.text(),self.symbols())
    def test_canonical_misaligned(self):
        for a in m.ADDRESSES:
            self.assertEqual(a&7,3)
            self.assertEqual(a>>39, (1<<25)-1 if (a>>38)&1 else 0)
    def test_readonly_probe(self):
        text=Path(m.__file__).with_name('scalar_misalign789_probe.tcl').read_text()
        self.assertNotIn('force ',text);self.assertNotIn('deposit ',text)
        self.assertIn('dcache_req_ports_o',text)
        self.assertIn('i_store_unit.st_valid',text)
        self.assertIn('SCALAR_MISALIGN_PROBE_ERROR',text)
if __name__=='__main__':unittest.main()
