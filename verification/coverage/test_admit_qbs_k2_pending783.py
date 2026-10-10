"""Focused prefix, native identity and parent-only publication rejection tests."""
import copy
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import admit_qbs_k2_pending783 as app


class AdmissionTests(unittest.TestCase):
    def fixture(self):
        row=dict(width=4,checksum='19',bits='0x1')
        old=dict(design={'shape':'hash'},tests=['historical%d'%i for i in range(782)],
                 input_hashes={'/old':'a'*64},metrics={m:{'scope':dict(row)} for m in app.COUNTS})
        new=copy.deepcopy(old)
        new.update(tests=[str(app.RUN/'code.vdb')],input_hashes={'/new':'b'*64})
        for rows in new['metrics'].values():rows['scope']['bits']='0x2'
        return old,new

    def union(self,old,new):
        with patch.object(app,'COUNTS',{m:1 for m in app.COUNTS}):
            return app.full_union(old,new)

    def test_exact_prefix_or(self):
        old,new=self.fixture();out=self.union(old,new)
        self.assertEqual(out['tests'][:782],old['tests'])
        self.assertEqual(len(out['tests']),783)
        self.assertTrue(all(r['scope']['bits']=='0x3' for r in out['metrics'].values()))
        self.assertEqual(old['metrics']['line']['scope']['bits'],'0x1')

    def test_duplicate_vdb(self):
        old,new=self.fixture();old['tests'][0]=new['tests'][0]
        with self.assertRaises(ValueError):self.union(old,new)

    def test_short_prefix(self):
        old,new=self.fixture();old['tests'].pop()
        with self.assertRaises(ValueError):self.union(old,new)

    def test_missing_metric(self):
        old,new=self.fixture();del new['metrics']['fsm']
        with self.assertRaises(ValueError):self.union(old,new)

    def test_checksum_drift(self):
        old,new=self.fixture();new['metrics']['line']['scope']['checksum']='20'
        with self.assertRaises(ValueError):self.union(old,new)

    def test_out_of_width(self):
        old,new=self.fixture();new['metrics']['cond']['scope']['bits']='0x10'
        with self.assertRaises(ValueError):self.union(old,new)

    def test_conflicting_pin(self):
        old,new=self.fixture();new['input_hashes']['/old']='c'*64
        with self.assertRaises(ValueError):self.union(old,new)

    def native(self):
        sim=ET.fromstring('<test><srctest cmdline="simv +seed=1" seed="1" starttime="10" finishtime="20" /></test>')
        sim[0].set('workdir',str(app.RUN))
        args=ET.Element('vcm_args',compvdbpath='compiled')
        for metric in ('branch','cond','fsm','line','tgl'):
            ET.SubElement(args,'vcm_arg_data',vcm_opt='-cm '+metric)
        return sim,args,dict(command=['simv','+seed=1'])

    def test_native_identity(self):
        sim,args,record=self.native()
        result=app.native_identity(sim,args,record,'compiled')
        self.assertTrue(result['XML_teststatus_is_not_PASS_authority'])

    def test_native_drift(self):
        for key,value in (('cmdline','simv +wrong'),('workdir','wrong'),('seed','2'),('finishtime','10')):
            with self.subTest(key=key):
                sim,args,record=self.native();sim[0].set(key,value)
                with self.assertRaises(ValueError):app.native_identity(sim,args,record,'compiled')

    def test_missing_toggle(self):
        sim,args,record=self.native();args.remove(args[-1])
        with self.assertRaises(ValueError):app.native_identity(sim,args,record,'compiled')

    def test_no_implicit_admission(self):
        with patch.object(sys,'argv',['helper','admit','--output',str(app.life.OUT/'not-created')]), \
                patch.object(app,'evaluate',side_effect=AssertionError('must not evaluate')):
            with self.assertRaises(ValueError):app.main()


if __name__=='__main__':unittest.main()
