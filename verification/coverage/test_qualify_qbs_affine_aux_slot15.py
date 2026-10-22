import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import qualify_qbs_affine_aux_slot15 as q


class WaveTests(unittest.TestCase):
    def fixture(self):
        decl = {'ara_tb.rst_n':dict(code='r'),q.run.SCOPE+'.entry_valid_q':dict(code='v')}
        for slot in range(16): decl[q.run.SCOPE+'.entry_state_q[%d]'%slot]=dict(code='s%d'%slot)
        before = dict(r='1',v='1'*16,**{'s%d'%i:'001' for i in range(16)})
        reset = dict(before,r='0',v='0'*16)
        release = dict(reset,r='1')
        allocated = dict(release,v='1'*16,**{'s%d'%i:'000' for i in range(16)})
        return [('declarations',decl),(10,before,reset),(50,reset,release),(60,release,allocated)]

    def test_all_slots_and_slot15_reuse(self):
        result = q.all_slots(iter(self.fixture()))
        self.assertEqual(len(result['reused_slots']),16)
        self.assertEqual(result['reused_slots'][15]['allocated_state'],0)

    def test_wrong_pre_reset_slot_state(self):
        events = self.fixture(); events[1][1]['s14']='010'
        with self.assertRaises(ValueError): q.all_slots(iter(events))

    def test_invalid_slot15(self):
        events = self.fixture(); events[1][1]['v']='0'+'1'*15
        with self.assertRaises(ValueError): q.all_slots(iter(events))

    def test_reset_state_cleared_instead_of_retained(self):
        events = self.fixture(); events[1][2]['s15']='000'
        with self.assertRaises(ValueError): q.all_slots(iter(events))

    def test_reuse_wrong_stage(self):
        events = self.fixture(); events[-1][2]['s15']='001'
        with self.assertRaises(ValueError): q.all_slots(iter(events))

    def test_missing_reuse(self):
        events = self.fixture(); events[-1][2]['v']='0'+'1'*15
        with self.assertRaises(ValueError): q.all_slots(iter(events))

    def test_population_adapter_only(self):
        ns = dict(q.old.collect.__globals__)
        function = q.collector(ns)
        self.assertIn(760,function.__code__.co_consts)
        self.assertNotIn(746,function.__code__.co_consts)
        self.assertEqual(q.old.BASE.name,'external-reset-fpu-half-offline-admitted-746-agent-20261007-01')

    def test_packed_bit15_not_bit0(self):
        c = q.run.configuration('aux')
        decl = {name:dict(code=code) for name,code in (
            ('ara_tb.clk','c'),('ara_tb.rst_n','r'),(c['ext_target'],'s'),
            (q.run.SCOPE+'.entry_valid_q','v'))}
        events = [('declarations',decl),(1,{},dict(c='0',r='1',s='001',v='1'+'0'*15)),
                  (2,{},dict(c='1',r='1',s='001',v='0'*15+'1'))]
        with tempfile.TemporaryDirectory() as tmp:
            source,selected = Path(tmp)/'source.vcd',Path(tmp)/'selected.vcd'
            source.write_text('mock source bytes')
            with patch.object(q,'parse',side_effect=lambda path:iter(events)), \
                 patch.object(q,'all_slots',return_value={}):
                binding = q.selected_wave(source,selected,c)
            self.assertEqual(binding['selected_guard_bit'],15)
            self.assertEqual(binding['mda_index'],15)
            text = selected.read_text()
            self.assertIn('#1\n0a\n1b\nb001 c\n1d\n',text)
            self.assertIn('#2\n1a\n1b\nb001 c\n0d\n',text)


if __name__ == '__main__': unittest.main()
