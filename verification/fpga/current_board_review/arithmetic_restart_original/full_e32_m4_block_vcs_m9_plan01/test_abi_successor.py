"""Correct only the test address: actual linked stack, frame and SD offset."""
from copy import deepcopy
import unittest
import checker as c
from host_records import Builder

class ABI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=c.specification();cls.rows=list(Builder(cls.spec).abi())
    def prefix(self):
        state=c.Strict(self.spec)
        for row in self.rows[:-2]:state.consume(row)
        return state
    def test_actual_linked_frame_saved_RA(self):
        state=self.prefix();row=self.rows[-2];pc=int(row['pc'],16)
        self.assertEqual(self.spec['backend']['symbols']['__stack_top'],0x800ffff0)
        self.assertEqual(self.spec['backend']['code'][str(self.spec['body_start'])],0x716d)
        self.assertEqual(state.code[pc],0xe606)
        desc=c.memory_op(state.code[pc])
        self.assertEqual((desc['base'],desc['register'],desc['size'],desc['offset']),(2,1,8,264))
        expected=state.s['__stack_top']-272+264
        self.assertEqual((expected,state.regs[2]+desc['offset'],int(row['mem_addr'],16)),(0x800fffe8,)*3)
        state.consume(row);state.consume(self.rows[-1])
        self.assertEqual(state.value(expected,8),0x80000052)
        self.assertEqual((state.csr_count,state.bss_next),(5,state.s['__bss_end']))
        self.assertTrue(state.main_entered and state.body_entered)
    def test_old_wrong_absolute_address_rejected(self):
        with self.assertRaises(ValueError):self.prefix().consume(dict(self.rows[-2],mem_addr='00000000800ffff8'))
    def test_wrong_BE_or_value_rejected(self):
        for k,v in (('mem_wmask','0f'),('mem_wdata','0000000000000001')):
            with self.subTest(key=k),self.assertRaises(ValueError):self.prefix().consume(dict(self.rows[-2],**{k:v}))
    def test_unknown_RA_not_defaulted(self):
        state=self.prefix();del state.regs[1]
        with self.assertRaises(ValueError):state.consume(self.rows[-2])

if __name__=='__main__':unittest.main(verbosity=2)
