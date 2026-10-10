import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import admit_narrow_source_group as p


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.record=dict(output=str(p.CANDIDATE),status=p.gain.POSITIVE,primary_fresh_gain=True,qualification=str(p.gain.QUAL),
            qualification_seal=p.gain.QUAL_SEAL,full_OR_instances=6162,exact735_prefix=True,baseline_tests=736,
            proposed_population=737,baseline=str(p.BASE),baseline_seal=p.BASE_SEAL,
            plan=str(p.PLAN),plan_seal=p.PLAN_SEAL,raw_delta=dict(line=1,cond=0,branch=0,fsm=0),coverage_admitted=False,
            application_approval=False,DVE_native_exclusion_qualified=False,native_cycle_qualified=False)

    def test_positive_model_only_not_actual_gain(self):p.gate(self.record)

    def test_zero_gain_and_HOLD_rejected(self):
        for key,value in [('raw_delta',dict(line=0,cond=0,branch=0,fsm=0)),('status',p.gain.HOLD),('primary_fresh_gain',False)]:
            record=copy.deepcopy(self.record);record[key]=value
            with self.assertRaises(ValueError):p.gate(record)

    def test_prefix_population_missing_OR_or_foreign_qualification_rejected(self):
        for key,value in [('exact735_prefix',False),('baseline_tests',735),('proposed_population',738),
                          ('full_OR_instances',6161),('qualification_seal','foreign')]:
            record=copy.deepcopy(self.record);record[key]=value
            with self.assertRaises(ValueError):p.gate(record)

    def test_waiver_timing_or_application_promotion_rejected(self):
        for key in ('coverage_admitted','application_approval','DVE_native_exclusion_qualified','native_cycle_qualified'):
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
            record=Path(temp)/'reviewed.json';proposal={'population':735}
            p.life.save(record,proposal);seal=p.life.digest(record)
            p.approval(record,seal,proposal,True)
            with self.assertRaises(ValueError):p.approval(record,seal,{'population':734},True)

    def test_fingerprint_serialization_matches_frozen_save(self):
        with tempfile.TemporaryDirectory(dir=p.OUT) as temp:
            root=Path(temp);products={'status.json':{'coverage_admitted':True,'checks':2130}}
            p.life.save(root/'status.json',products['status.json']);text='design\nsingle\n'
            (root/'combined-inputs.txt').write_text(text)
            self.assertEqual(p.fingerprints(root,products,text),
                             {str(x):p.life.digest(x) for x in root.iterdir()})

    def test_exact_parent_plan_and_formal736_seals_only(self):
        for key,value in (('baseline',str(p.gain.BASE)),('baseline_seal',p.gain.BASE_SEAL),
                          ('plan','/foreign/plan.json'),('plan_seal','a'*64)):
            record=copy.deepcopy(self.record);record[key]=value
            with self.assertRaises(ValueError):p.gate(record)

    def test_foreign_qualification_path_rejected(self):
        record=copy.deepcopy(self.record);record['qualification']='/foreign/qualification.json'
        with self.assertRaises(ValueError):p.gate(record)

    def test_bad_header_rejected_before_expensive_candidate_replay(self):
        with patch.object(p.life,'digest',return_value=p.GAIN_SHA), \
             patch.object(p.life,'read_bound',return_value=dict(self.record,status=p.gain.HOLD)), \
             patch.object(p.gain,'verify') as verify:
            with self.assertRaises(ValueError):p.evaluate(p.CANDIDATE,p.CANDIDATE_SEAL)
            verify.assert_not_called()

    def test_no_authorized_admit_cannot_evaluate_or_write(self):
        with patch.object(p,'evaluate') as evaluate:
            with self.assertRaises(ValueError):
                p.main(['admit','--candidate',str(p.OUT/'synthetic-candidate'),'--candidate-seal','a'*64,
                        '--output',str(p.OUT/'synthetic-formal737'),'--seal','b'*64])
            evaluate.assert_not_called()

    def test_wrong_candidate_or_seal_rejected_before_reads(self):
        with patch.object(p.life,'read_bound') as read:
            for directory,seal in ((p.OUT/'foreign-candidate',p.CANDIDATE_SEAL),(p.CANDIDATE,'a'*64)):
                with self.assertRaises(ValueError):p.evaluate(directory,seal)
            read.assert_not_called()

    def test_wrong_candidate_output_in_header_rejected(self):
        record=copy.deepcopy(self.record);record['output']=str(p.OUT/'foreign-candidate')
        with self.assertRaises(ValueError):p.gate(record)


if __name__=='__main__':unittest.main()
