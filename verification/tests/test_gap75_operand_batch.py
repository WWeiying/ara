import copy
import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
import run_gap75_operand_batch as batch


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.old={'metrics':{'line':{'unit':dict(width=4,checksum='same',bits='0x8')}}}
        self.new={'metrics':{'line':{'unit':dict(width=4,checksum='same',bits='0xc')}}}
        self.points=[dict(module='operand_queue',scope='unit',metric='line',
                          source='rtl',raw_index='1')]
    def test_exact_new_hit(self):
        self.assertEqual(batch.historical_target_hits(self.new,self.old,self.points,
            {'rtl':'hash'},{'rtl':'hash'})['count'],1)
    def test_no_gain(self):
        self.assertEqual(batch.historical_target_hits(self.old,self.old,self.points,
            {'rtl':'hash'},{'rtl':'hash'})['count'],0)
    def test_source_or_shape_drift_rejected(self):
        with self.assertRaises(RuntimeError):
            batch.historical_target_hits(self.new,self.old,self.points,{'rtl':'hash'},{'rtl':'different'})
        new=copy.deepcopy(self.new);new['metrics']['line']['unit']['checksum']='different'
        with self.assertRaises(RuntimeError):
            batch.historical_target_hits(new,self.old,self.points,{'rtl':'hash'},{'rtl':'hash'})
    def test_not_a_historical_zero_rejected(self):
        points=copy.deepcopy(self.points);points[0]['raw_index']='0'
        with self.assertRaises(RuntimeError):
            batch.historical_target_hits(self.new,self.old,points,{'rtl':'hash'},{'rtl':'hash'})
    def test_changed_dispatcher_not_compared(self):
        points=copy.deepcopy(self.points);points[0]['module']='ara_dispatcher'
        self.assertEqual(batch.historical_target_hits(self.new,self.old,points,{}, {})['count'],0)


if __name__=='__main__':unittest.main()
