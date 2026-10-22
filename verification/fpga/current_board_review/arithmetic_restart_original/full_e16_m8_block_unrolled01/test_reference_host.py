"""Actual lowered16 phase/footprint negatives; no raw or reference execution."""
from copy import deepcopy
import json
import sys
import unittest
sys.dont_write_bytecode=True
import prepare as p
from lifecycle import Lifecycle
from model import generate,words
HERE=p.HERE

class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend=json.loads((HERE/'proof.json').read_text())['backends']['spike']
        cls.s=cls.backend['symbols'];cls.code={int(pc):i for pc,i in cls.backend['code'].items()}
        cls.entries=[cls.backend['helpers'][f'op_{i}'][0]['pc'] for i in range(25)]
        cls.init=json.loads((HERE/'lowering.json').read_text())['spike']['initializer']
    def lifecycle(self):return Lifecycle(self.s,self.code,self.entries)
    def boot(self):
        obj=self.lifecycle()
        for addr in range(self.s['__bss_start'],self.s['__bss_end'],8):obj.store(obj.bss_pc,0x0002b023,addr,8,0)
        obj.enter(self.s['main']);obj.enter(self.s['arithmetic_main']);return obj
    def stores(self,obj,drop=None):
        for i,row in enumerate(self.init):
            if i==drop:continue
            obj.store(row['pc'],row['insn'],self.s['out']+row['offset'],row['size'],0x005b005b if row['size']==4 else 0x005b005b005b005b)
    def test_complete_typed128SD_SW4(self):
        obj=self.boot();self.stores(obj);obj.enter(self.entries[0])
        self.assertEqual((obj.calls,obj.stores),(1,0));self.assertEqual(sum(row['size'] for row in self.init),1028)
    def test_deleted_initializer(self):
        obj=self.boot()
        with self.assertRaises(ValueError):self.stores(obj,drop=10)
    def test_e8_sentinel_rejected(self):
        obj=self.boot();row=self.init[0]
        with self.assertRaises(ValueError):obj.store(row['pc'],row['insn'],self.s['out']+row['offset'],8,0x5b5b5b5b5b5b5b5b)
    def test_wrong_tail_width_value(self):
        index=next(i for i,r in enumerate(self.init) if r['size']==4);obj=self.boot()
        for row in self.init[:index]:obj.store(row['pc'],row['insn'],self.s['out']+row['offset'],8,0x005b005b005b005b)
        row=self.init[index]
        for size,value in ((2,0x5b5b),(8,0x005b005b005b005b),(4,0x5b5b5b5b)):
            with self.assertRaises(ValueError):deepcopy(obj).store(row['pc'],row['insn'],self.s['out']+1024,size,value)
    def test_startupBSS_exact_phase(self):
        obj=self.lifecycle()
        for value,address in ((1,obj.next_bss),(0,obj.next_bss+8)):
            with self.assertRaises(ValueError):obj.store(obj.bss_pc,0x0002b023,address,8,value)
        with self.assertRaises(ValueError):obj.enter(self.s['main'])
        obj=self.boot()
        with self.assertRaises(ValueError):obj.store(obj.bss_pc,0x0002b023,self.s['out']+1024,8,0)
    def test_guard_upperbyte_and_raw_encoding(self):
        seeds,rows,pool,masks=generate();raw=b''.join(pool[ix].to_bytes(64,'little') for ix in rows[0]['indices'])[:1028]
        self.assertEqual(raw,words([91]*514));self.assertEqual(raw[-4:],bytes.fromhex('5b005b00'))
        self.assertEqual([len(words(s['a'])) for s in seeds],[1024]*3)
        self.assertTrue(all(not any(m[64:]) for m in masks))
        for pos in (0,1,1024,1025,1026,1027):
            changed=bytearray(raw);changed[pos]^=1;self.assertNotEqual(bytes(changed),raw)
    def test_declaredphysical_vs_checked(self):
        obj=self.boot()
        with self.assertRaises(ValueError):obj.store(self.init[0]['pc'],self.init[0]['insn'],self.s['out']+1032,8,0)
        self.assertEqual(1024*2,2048);self.assertEqual(1026*2,2052)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    p.save(HERE/'reference_host_result.json',dict(status='PASS' if result.wasSuccessful() else 'FAIL',tests=result.testsRun,
        errors=len(result.errors),failures=len(result.failures),raw_reads=0,reference_runs=0,DUT_runs=0))
    raise SystemExit(not result.wasSuccessful())
