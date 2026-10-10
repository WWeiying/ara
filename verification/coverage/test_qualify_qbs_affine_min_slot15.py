import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import qualify_qbs_affine_min_slot15 as q
from test_qualify_qbs_affine_aux_slot15 import WaveTests


class MinWave(unittest.TestCase):
    def fixture(self):
        events = WaveTests().fixture()
        for _,before,after in events[1:]:
            for values in (before,after):
                for slot in range(16):
                    if values['s%d'%slot] == '001': values['s%d'%slot]='011'
        return events

    def test_all_min_slots(self):
        result = q.all_slots(iter(self.fixture()))
        self.assertEqual(result['pre_reset']['states'],[3]*16)
        self.assertEqual(result['reused_slots'][15]['retained_state'],3)

    def test_aux_cannot_pass(self):
        with self.assertRaises(ValueError): q.all_slots(iter(WaveTests().fixture()))

    def test_one_slot_wrong_or_invalid(self):
        for invalid in ('phase','valid','reuse'):
            events = self.fixture()
            if invalid == 'phase': events[1][1]['s14']='010'
            if invalid == 'valid': events[1][1]['v']='0'+'1'*15
            if invalid == 'reuse': events[-1][2]['s15']='011'
            with self.assertRaises(ValueError): q.all_slots(iter(events))

    def test_native_bit15_min_projection(self):
        c = q.run.configuration('min_scale')
        decl = {name:dict(code=code) for name,code in (
            ('ara_tb.clk','c'),('ara_tb.rst_n','r'),(c['ext_target'],'s'),
            (q.run.SCOPE+'.entry_valid_q','v'))}
        events = [('declarations',decl),(1,{},dict(c='0',r='1',s='011',v='1'+'0'*15))]
        with tempfile.TemporaryDirectory() as tmp:
            source,selected = Path(tmp)/'source',Path(tmp)/'selected'
            source.write_text('mock')
            with patch.object(q.template,'parse',side_effect=lambda p:iter(events)), \
                 patch.object(q,'all_slots',return_value={}):
                binding = q.selected_wave(source,selected,c)
            self.assertEqual(binding['selected_guard_bit'],15)
            self.assertEqual(binding['mda_index'],15)
            self.assertIn('b011 c\n1d\n',selected.read_text())


if __name__ == '__main__': unittest.main()
