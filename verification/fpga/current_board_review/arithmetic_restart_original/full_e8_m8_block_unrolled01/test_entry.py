import hashlib
import json
from pathlib import Path
import re
import unittest
from lifecycle import INIT, Lifecycle
from model import generate

HERE=Path(__file__).resolve().parent

class EntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=json.loads((HERE/'spike/symbols.json').read_text())
        cls.code={int(m[1],16):int(m[2],16) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',
            (HERE/'spike/program.dis').read_text(),re.M)}
        cls.entry=json.loads((HERE/'proof.json').read_text())['backends']['spike']['helpers']['op_0'][0]['pc']
    def state(self):
        state=Lifecycle(self.s,self.code,[self.entry])
        for addr in range(self.s['__bss_start'],self.s['__bss_end'],8):
            state.store(0x80000046,0x0002b023,addr,8,0)
        state.enter(self.s['main']);state.enter(self.s['arithmetic_main'])
        return state
    def fill(self,state,count=129):
        for i in range(count):
            pc,insn,width,offset=INIT[i]
            state.store(pc,insn,self.s['out']+offset,width,0x5b5b if width==2 else 0x5b5b5b5b5b5b5b5b)
    def test_all4095_block_model_matches_frozen_feasibility(self):
        seeds,rows,pool,masks=generate()
        original=json.loads((HERE.parent/'m8_block64_feasibility01/host_result01.json').read_text())['shapes']['e8_m8']
        data=b''.join(v.to_bytes(64,'little') for v in pool)
        table=b''.join(i.to_bytes(2,'little') for r in rows for i in r['indices'])
        raw=b''.join(b''.join(pool[i].to_bytes(64,'little') for i in r['indices'])[:1026] for r in rows)
        self.assertEqual(len(rows),4095);self.assertEqual(len(pool),3768)
        self.assertEqual(hashlib.sha256(data).hexdigest(),original['pool_sha256'])
        self.assertEqual(hashlib.sha256(table).hexdigest(),original['index_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),original['oracle_bytes_sha256'])
        self.assertTrue(all(len(s['a'])==len(s['b'])==1024 for s in seeds))
        self.assertEqual(masks[0],b'\xff'*128)
    def test_full4095_initializer_lifecycle(self):
        state=self.state()
        for _ in range(4095):self.fill(state);state.enter(self.entry)
        self.assertEqual(state.calls,4095);self.assertEqual(state.stores,0)
    def test_missing_initialization(self):
        state=self.state()
        with self.assertRaises(ValueError):state.enter(self.entry)
    def test_missing_last_sd(self):
        state=self.state();self.fill(state,128)
        with self.assertRaises(ValueError):state.enter(self.entry)
    def test_wrong_store_fields(self):
        pc,insn,w,_=INIT[0];out=self.s['out'];value=0x5b5b5b5b5b5b5b5b
        for values in ((pc+2,insn,out,w,value),(pc,insn^1,out,w,value),(pc,insn,out+8,w,value),
                       (pc,insn,out,4,value),(pc,insn,out,w,0),(pc,insn,out-1,w,value)):
            with self.subTest(values=values),self.assertRaises(ValueError):self.state().store(*values)
    def test_wide_tail(self):
        state=self.state();self.fill(state,100)
        with self.assertRaises(ValueError):state.store(INIT[100][0],INIT[100][1],self.s['out']+1024,8,0x5b5b)
    def test_duplicate_tail(self):
        state=self.state();self.fill(state)
        with self.assertRaises(ValueError):state.store(INIT[100][0],INIT[100][1],self.s['out']+1024,2,0x5b5b)
    def test_skip_each_store_rejected_even_if_shadow_unchanged(self):
        for omitted in range(129):
            state=self.state()
            with self.subTest(omitted=omitted),self.assertRaises(ValueError):
                for i,(pc,insn,width,offset) in enumerate(INIT):
                    if i!=omitted:
                        state.store(pc,insn,self.s['out']+offset,width,
                            0x5b5b if width==2 else 0x5b5b5b5b5b5b5b5b)
                state.enter(self.entry)
    def test_exact_schedule_partition(self):
        self.assertEqual(len(INIT),129)
        self.assertEqual([(w,o) for _,_,w,o in INIT],
            [(8,i*8) for i in range(100)]+[(2,1024)]+[(8,i*8) for i in range(100,128)])
        covered=[j for _,_,w,o in INIT for j in range(o,o+w)]
        self.assertEqual(sorted(covered),list(range(1026)))
    def test_late_boot_write(self):
        state=self.state()
        with self.assertRaises(ValueError):state.store(0x80000046,0x0002b023,self.s['out']+1024,8,0)
    def test_incomplete_boot(self):
        state=Lifecycle(self.s,self.code,[self.entry])
        with self.assertRaises(ValueError):state.enter(self.s['main'])
    def test_code_drift(self):
        code=dict(self.code);code[INIT[0][0]]^=1
        with self.assertRaises(ValueError):Lifecycle(self.s,code,[self.entry])

if __name__=='__main__':unittest.main()
