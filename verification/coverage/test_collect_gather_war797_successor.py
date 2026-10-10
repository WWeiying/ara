"""Focused real-trace replay and corruptions, without any simulator launch."""
import copy
from dataclasses import replace
import unittest
from unittest.mock import patch

import collect_gather_war797_successor as s

g=s.g


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=g.life.read_bound(s.PRE,s.PRE_SHA)
        cls.ref=g.reference(cls.pre)
        cls.fixture=g.mature.vc._parse_vector_trace(s.RUN/'vector_trace.csv')
        cls.native=s.corrected_native()

    def replay(self,change=None):
        fixture=copy.deepcopy(self.fixture)
        if change:change(fixture[2])
        with patch.object(g.mature.vc,'_parse_vector_trace',return_value=fixture):
            return type(self).native(s.RUN,self.ref,self.pre['symbols'],self.pre)

    def test_real_native_full_strict(self):
        r=self.replay();v=r['architectural_vector_diff']
        self.assertEqual(len(r['primary_writers']),16)
        self.assertEqual(v['compared_bytes'],16384)
        self.assertEqual(v['skipped_unknown_bytes'],0)
        self.assertEqual(v['status'],'PASS')

    def test_store_context_none_is_real_not_skipped_writer(self):
        stores=[a for a in self.fixture[2].values() if not a.use_vd]
        self.assertTrue(any(a.vl is None and a.eew is None for a in stores))
        self.assertTrue(all(not a.writes for a in stores))

    def test_wrong_gather_producer_rejected(self):
        def change(aa):aa[5].writes[0]=replace(aa[5].writes[0],source=3)
        with self.assertRaisesRegex(ValueError,'Exact Gather/LD producer'):self.replay(change)

    def test_writer_active_context_still_required(self):
        with self.assertRaisesRegex(ValueError,'Exact full active group'):
            self.replay(lambda aa:setattr(aa[5],'vl',None))

    def test_missing_writer_rejected(self):
        with self.assertRaisesRegex(ValueError,'Required native activity missing'):
            self.replay(lambda aa:aa.pop(5))

    def test_missing_byte_rejected(self):
        def change(aa):aa[5].writes[0]=replace(aa[5].writes[0],be=0xfe)
        with self.assertRaisesRegex(ValueError,'Every known primary byte'):self.replay(change)

    def test_wrong_byte_rejected(self):
        def change(aa):aa[5].writes[0]=replace(aa[5].writes[0],data=aa[5].writes[0].data^1)
        with self.assertRaisesRegex(ValueError,'Every known primary byte'):self.replay(change)

    def test_unknown_byte_rejected(self):
        def change(aa):aa[5].writes[0]=replace(aa[5].writes[0],known_be=0xfe)
        with self.assertRaisesRegex(ValueError,'Exact accepted write'):self.replay(change)

    def test_duplicate_byte_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate accepted producer byte'):
            self.replay(lambda aa:aa[5].writes.append(aa[5].writes[0]))

    def test_original_pins_unchanged(self):
        self.assertEqual(g.life.digest(g.ROOT/'verification/coverage/gather_war797.py'),s.ORIGINAL_SHA)
        self.assertEqual(g.life.digest(s.RUN.with_name(s.RUN.name+'.prepared.json')),s.SEAL)
        s.source_pins()


if __name__=='__main__':unittest.main()
