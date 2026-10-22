import copy
import unittest
import preflight_mask_b_sext4 as m


class Tests(unittest.TestCase):
    def test_independent_signed_gold_and_complete_image(self):
        self.assertEqual(m.gold(0),[0xffffffffffff8001,64,0,64,8,0,0,0])
        self.assertEqual(m.gold(1),[32767,64,0,64,8,0,0,0])
        for phase in range(2):
            self.assertEqual(len(m.image(phase)),128)
            self.assertEqual(int.from_bytes(m.image(phase)[126:128],'little'),0x3100+63*37)
        with self.assertRaises(ValueError): m.image(2)

    def test_actual780_source_compiled_EL_binding(self):
        target=m.targets()
        self.assertEqual((target['point']['raw_index'],target['point']['native_id'],target['point']['vector']),(70,'5','6'))
        self.assertFalse(target['excluded'])
        self.assertFalse(target['before_hit'])

    def test_hit_wrong_layout_and_vector_rejected(self):
        design=m.inventory.s.Design(m.inventory.old.BUILD/'sim/simv.vdb')
        definition=design.definition(m.SCOPE,'branch')
        row=dict(width=101,checksum=None,bits='0')
        m.bind(row,definition)
        for bad in (dict(row,bits=hex(1<<(100-70))),dict(row,width=100),dict(row,checksum='foreign')):
            with self.assertRaises(ValueError):m.bind(bad,definition)
        bad=copy.deepcopy(definition)
        group=next(g for g in bad.iter('branch_spec') if g.get('id')=='5')
        vector=next(v for v in group.findall('branch_vector') if v.get('id')=='6')
        vector.set('vector','0'*len(vector.get('vector')))
        with self.assertRaises(ValueError):m.bind(row,bad)


if __name__=='__main__':unittest.main()
