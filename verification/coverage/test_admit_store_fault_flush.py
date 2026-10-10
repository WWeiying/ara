import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import admit_store_fault_flush as p


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.record=dict(status=p.gain.POSITIVE,primary_fresh_gain=True,qualification=str(p.gain.QUAL),
            qualification_seal=p.gain.QUAL_SEAL,full_OR_instances=6162,exact732_prefix=True,baseline_tests=732,
            proposed_population=733,raw_delta=dict(line=1,cond=0,branch=0,fsm=0),coverage_admitted=False,
            application_approval=False,DVE_native_exclusion_qualified=False,native_B_error_plus_addr_fault_timing_measured=False)

    def test_positive_model_only_not_actual_gain(self):p.gate(self.record)

    def test_zero_gain_and_HOLD_rejected(self):
        for key,value in [('raw_delta',dict(line=0,cond=0,branch=0,fsm=0)),('status',p.gain.HOLD),('primary_fresh_gain',False)]:
            record=copy.deepcopy(self.record);record[key]=value
            with self.assertRaises(ValueError):p.gate(record)

    def test_prefix_population_missing_OR_or_foreign_qualification_rejected(self):
        for key,value in [('exact732_prefix',False),('baseline_tests',731),('proposed_population',734),
                          ('full_OR_instances',6161),('qualification_seal','foreign')]:
            record=copy.deepcopy(self.record);record[key]=value
            with self.assertRaises(ValueError):p.gate(record)

    def test_waiver_timing_or_application_promotion_rejected(self):
        for key in ('coverage_admitted','application_approval','DVE_native_exclusion_qualified','native_B_error_plus_addr_fault_timing_measured'):
            record=copy.deepcopy(self.record);record[key]=True
            with self.assertRaises(ValueError):p.gate(record)

    def test_malformed_negative_or_bool_delta_rejected(self):
        for value in (-1,True,1.0):
            record=copy.deepcopy(self.record);record['raw_delta']['line']=value
            with self.assertRaises(ValueError):p.gate(record)

    def test_no_authorization_cannot_read_or_write_admission(self):
        with patch.object(p.life,'read_bound') as read:
            for authorized,seal in [(False,'a'*64),(True,None)]:
                with self.assertRaises(ValueError):p.approval(Path('/not-read'),seal,{},authorized)
            read.assert_not_called()

    def test_exact_reviewed_sidecar_and_drift_rejection(self):
        with tempfile.TemporaryDirectory(dir=p.OUT) as temp:
            record=Path(temp)/'reviewed.json';proposal={'population':733}
            p.life.save(record,proposal);seal=p.life.digest(record)
            p.approval(record,seal,proposal,True)
            with self.assertRaises(ValueError):p.approval(record,seal,{'population':734},True)

    def test_fingerprint_serialization_matches_frozen_save(self):
        with tempfile.TemporaryDirectory(dir=p.OUT) as temp:
            root=Path(temp);products={'status.json':{'coverage_admitted':True,'checks':134}}
            p.life.save(root/'status.json',products['status.json']);text='design\nsingle\n'
            (root/'combined-inputs.txt').write_text(text)
            self.assertEqual(p.fingerprints(root,products,text),
                             {str(x):p.life.digest(x) for x in root.iterdir()})


if __name__=='__main__':unittest.main()
