from copy import deepcopy
import unittest
from unittest.mock import patch
import prepare_sv39_masked_unit_fault_admission as m


class AdmissionTests(unittest.TestCase):
    def fixture(self):
        delta=dict(metrics=dict(line=0,cond=1,branch=0,fsm=0))
        state=dict(status='SV39_MASKED_FAULT_POSITIVE_RAW735_CANDIDATE_NOT_ADMITTED',baseline=735,
            proposed_tests=736,coverage_admitted=False,new_RTL_signoff=False,official_DVE_report=False,
            simulations_started=False,raw_delta=deepcopy(delta['metrics']),target493_hit=True)
        target=dict(scope=m.gain.p.SCOPE,metric='cond',raw_index=493,width=1140,checksum='1370170966',
                    before=False,sample=True,proposed=True)
        return state,delta,target

    def test_positive_candidate(self):m.gate(*self.fixture())
    def test_other_gain_without_target_hit_not_fabricated(self):
        s,d,t=self.fixture();s['target493_hit']=False;t['sample']=t['proposed']=False;m.gate(s,d,t)
    def test_zero_gain(self):
        s,d,t=self.fixture();d['metrics']['cond']=0;s['raw_delta']['cond']=0
        with self.assertRaises(ValueError):m.gate(s,d,t)
    def test_wrong_population(self):
        s,d,t=self.fixture();s['baseline']=734
        with self.assertRaises(ValueError):m.gate(s,d,t)
    def test_admitted_candidate_rejected(self):
        s,d,t=self.fixture();s['coverage_admitted']=True
        with self.assertRaises(ValueError):m.gate(s,d,t)
    def test_bool_metric(self):
        s,d,t=self.fixture();s['raw_delta']['cond']=d['metrics']['cond']=True
        with self.assertRaises(ValueError):m.gate(s,d,t)
    def test_invented_target_hit(self):
        s,d,t=self.fixture();s['target493_hit']=False
        with self.assertRaises(ValueError):m.gate(s,d,t)
    def test_wrong_compiled_target(self):
        for field,value in [('raw_index',494),('metric','branch'),('checksum','0'),('scope','foreign')]:
            s,d,t=self.fixture();t[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.gate(s,d,t)
    def test_before_hit_rejected(self):
        s,d,t=self.fixture();t['before']=True
        with self.assertRaises(ValueError):m.gate(s,d,t)
    def test_unauthorized_admit_does_not_check_or_write(self):
        with patch.object(m,'check') as checker:
            with self.assertRaises(ValueError):m.admit(None,None,None,'UNAUTHORIZED')
            checker.assert_not_called()


if __name__=='__main__':unittest.main()
