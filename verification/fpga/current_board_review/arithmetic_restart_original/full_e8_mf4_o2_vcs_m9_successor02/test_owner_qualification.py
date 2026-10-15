"""Focused successor negatives, no reference/DUT or scalar-oracle replay."""
from copy import deepcopy
import json
from pathlib import Path
import time
import unittest
import checker as c

class OwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=c.specification(c.SHAPE);cls.gold=c.read(c.REF/c.SHAPE/'model.json')
        cls.template=c.MemoryOwners(cls.spec)
        cls.targets=[i for i,x in enumerate(cls.template.expected) if x['active_target']]
        cls.empty=[i for i,x in enumerate(cls.template.expected) if not x['required']]
        cls.completed=cls.feed()

    @classmethod
    def feed(cls,drop=None):
        # Replay actual PC/insn/model membership, not a DUT or synthetic VL hint.
        o=c.MemoryOwners.__new__(c.MemoryOwners)
        o.lookup=cls.template.lookup;o.expected=cls.template.expected
        o.arch={};o.live={};o.memory_arch=[];o.retired=[];o.allocs=o.dones=0
        for seq,x in enumerate(o.expected):
            row=dict(event='arch_start',order=str(seq),port='-1',trans_id='0',insn=f'{x["insn"]:08x}',pc=f'{x["pc"]:016x}')
            o.consume(row)
            if x['required'] and seq!=drop:
                o.consume(dict(row,event='uop_alloc',port='0'))
                o.consume(dict(row,event='uop_done',port='0'))
            o.consume(dict(row,event='retire'))
        return o

    def test_full_enumeration_and_empty_elision(self):
        self.assertEqual(len(self.targets),117);self.assertEqual(len(self.empty),72)
        self.assertEqual(sum(g['op']==24 for g in self.gold),189)
        independent=[g for g in self.gold if g['op']==24 and g['vl']>g['vstart']]
        self.assertEqual([self.template.expected[i]['call'] for i in self.targets],[g['ordinal'] for g in independent])
        got=self.completed.finish()
        self.assertEqual((got['required_nonempty_helpers'],got['required_active_memory_targets'],got['all_uop_allocs']),
                         (20475,117,20592))

    def test_each117_complete_target_pair_deleted(self):
        for index in self.targets:
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'Missing nonempty memory owner'):
                self.feed(drop=index).finish()

    def test_wrong_target_owner_id(self):
        x=self.template.expected[self.targets[0]]
        for bad in (dict(order='1'),dict(trans_id='2')):
            o=c.MemoryOwners(self.spec)
            r=dict(event='arch_start',order='0',port='-1',trans_id='0',insn=f'{x["insn"]:08x}',pc=f'{x["pc"]:016x}')
            o.consume(r)
            with self.assertRaises(ValueError):o.consume(dict(r,event='uop_alloc',port='0',**bad))
        o=c.MemoryOwners(self.spec);o.consume(r);o.consume(dict(r,event='uop_alloc',port='0'))
        with self.assertRaises(ValueError):o.consume(dict(r,event='uop_done',port='1'))

    def test_forged_actual_target_vl(self):
        for g,want in ((next(g for g in self.gold if g['op']==24 and g['vl']==0),1),
                       (next(g for g in self.gold if g['op']==24 and g['vl']>g['vstart']),0)):
            state=c.Strict(self.spec,self.gold)
            state.retired=1;state.helper='op_24';state.index=5;state.active=dict(ordinal=g['ordinal'])
            x=self.spec['backend']['helpers']['op_24'][5]
            row=dict(cycle='1',event='retire',order='1',port='0',trans_id='-1',pc=f'{x["pc"]:016x}',
                insn=f'{x["insn"]:08x}',rd='5',rd_wdata=f'{want:016x}',trap='0',
                mem_addr='0000000000000000',mem_rmask='00',mem_wmask='00',mem_wdata='0000000000000000')
            with self.assertRaisesRegex(ValueError,'Original helper VL'):state.consume(row)

if __name__=='__main__':
    began=time.monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OwnerTests))
    payload=dict(status='PASS_FOCUSED_OWNER_QUALIFICATION_HOST_ONLY' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun,failures=len(result.failures)+len(result.errors),elapsed_s=time.monotonic()-began,
        required_helpers=20475,active_targets=117,empty_targets=72,required_owners=20592,
        all117_pair_deletion_negatives=True,reference_runs=0,DUT_runs=0,
        pins={str(c.HERE/n):c.sha(c.HERE/n) for n in ('checker.py','test_owner_qualification.py')})
    with (c.HERE/'owner_host01.json').open('x') as f:json.dump(payload,f,indent=2);f.write('\n')
    raise SystemExit(not result.wasSuccessful())
