"""Small actual SoC-site transport tests; not a full reference or DUT run."""
from copy import deepcopy
import unittest
import checker as c
from host_records import Builder

class ByteTransport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=c.specification();state=c.Strict(spec);builder=Builder(spec)
        cls.sd=None
        for row in builder.records():
            pc=int(row['pc'],16)
            if row['mem_wmask']=='ff' and state.body_entered and int(row['mem_wdata'],16) and cls.sd is None:
                cls.sd=(deepcopy(state),dict(row))
            if state.life.active=='mask' and pc==state.life.path[-1]:
                cls.state=state;cls.row=dict(row);break
            state.consume(row)
        assert cls.sd is not None and int(cls.row['mem_wdata'],16)==c.MASK64
    def clone(self):
        # All model/code objects are immutable in these local mutation tests.
        from test_host import deepcopy as clone
        return clone(self.state)
    def test_full_XLEN_SB_positive(self):
        x=self.clone();x.consume(self.row)
        self.assertIsNone(x.life.active)
        self.assertEqual(x.value(int(self.row['mem_addr'],16),1),255)
    def test_same_enabled_byte_with_zero_upper(self):
        x=self.clone();x.consume(dict(self.row,mem_wdata='00000000000000ff'))
        self.assertIsNone(x.life.active)
    def test_wrong_enabled_byte(self):
        with self.assertRaises(ValueError):self.clone().consume(dict(self.row,mem_wdata='fffffffffffffffe'))
    def test_wrong_byte_enables_not_mask_derived_from_BE(self):
        for be in ('00','03','ff'):
            with self.subTest(be=be),self.assertRaises(ValueError):self.clone().consume(dict(self.row,mem_wmask=be))
    def test_SD_retains_all64bits(self):
        from test_host import deepcopy as clone
        state,row=self.sd;x=clone(state);pc=int(row['pc'],16);desc=c.memory_op(int(row['insn'],16))
        altered=int(row['mem_wdata'],16)^(1<<63);x.regs[desc['register']]=altered
        with self.assertRaises(ValueError):x.consume(dict(row,mem_wdata=f'{altered:016x}'))
    def test_marker_fixture_real_newline_and_literal_rejected(self):
        self.assertIn('\n',Builder.records.__code__.co_consts)
        self.assertNotIn('\\n',Builder.records.__code__.co_consts)
        c.console_gate(c.marker()+'\n',simulator=False)
        with self.assertRaises(ValueError):c.console_gate(c.marker()+'\\n',simulator=False)
    def test_no_premature_final_phase_completion(self):
        x=self.clone();pc=int(self.row['pc'],16);x.life.enter(pc,x.regs)
        with self.assertRaises(ValueError):x.life.leave(pc,x.regs)

if __name__=='__main__':unittest.main(verbosity=2)
