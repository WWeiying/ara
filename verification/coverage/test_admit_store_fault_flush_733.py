import copy
import unittest
from unittest.mock import patch

import admit_store_fault_flush_733 as p


class ExactAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record=p.life.read_bound(p.CANDIDATE/'candidate.json',p.CANDIDATE_SHA)
        cls.hits=p.life.read_bound(p.CANDIDATE/'target-hits.json',
            cls.record['output_pins'][str(p.CANDIDATE/'target-hits.json')])

    def test_actual_sealed_candidate_exact_three_gain_and_two_fresh_targets(self):
        p.identity(p.CANDIDATE,p.CANDIDATE_SHA);p.exact_record(self.record)
        self.assertEqual(self.record['raw_delta'],p.EXPECTED_DELTA)
        self.assertEqual([h['point']['raw_index'] for h in self.hits],[54,43])
        self.assertTrue(all(h['fresh_target_gain'] for h in self.hits))

    def test_foreign_candidate_or_seal_rejected(self):
        for directory,seal in [(p.CANDIDATE,'a'*64),(p.CANDIDATE.with_name('foreign'),p.CANDIDATE_SHA)]:
            with self.assertRaises(ValueError):p.identity(directory,seal)

    def test_predecessor_drift_rejected(self):
        with patch.object(p.life,'digest',return_value='a'*64):
            with self.assertRaisesRegex(ValueError,'predecessor drift'):p.identity(p.CANDIDATE,p.CANDIDATE_SHA)

    def test_wrong_population_baseline_or_gain_rejected(self):
        for key,value in [('proposed_population',734),('baseline_tests',733),('baseline_seal','foreign'),
            ('raw_delta',dict(line=1,cond=0,branch=1,fsm=0))]:
            record=copy.deepcopy(self.record);record[key]=value
            with self.assertRaises(ValueError):p.exact_record(record)

    def test_zero_gain_HOLD_rejected(self):
        record=copy.deepcopy(self.record);record['status']=p.frozen.gain.HOLD
        with self.assertRaises(ValueError):p.exact_record(record)

    def test_missing_conditional_fresh_hit_rejected(self):
        products={'target-hits.json':copy.deepcopy(self.hits)}
        products['target-hits.json'][1]['fresh_target_gain']=False
        with patch.object(p,'ORIGINAL_EVALUATE',return_value=(self.record,products,'text')):
            with self.assertRaisesRegex(ValueError,'conditional43'):p.evaluate(p.CANDIDATE,p.CANDIDATE_SHA)

    def test_adapter_pins_survive_serialized_output_preparation(self):
        products={'target-hits.json':copy.deepcopy(self.hits),'evidence-pins.json':{'/fixture/input':'a'*64}}
        with patch.object(p,'ORIGINAL_EVALUATE',return_value=(self.record,products,'text')),patch.object(p.life,'check'):
            _,result,_=p.evaluate(p.CANDIDATE,p.CANDIDATE_SHA)
        self.assertIn(p.__file__,result['evidence-pins.json'])
        self.assertIn(__file__,result['evidence-pins.json'])

    def test_main_restores_predecessor_after_failure_no_admission(self):
        original=p.frozen.evaluate
        with patch.object(p.frozen,'main',side_effect=ValueError('mock failure')):
            with self.assertRaisesRegex(ValueError,'mock failure'):
                p.main(['prepare','--candidate',str(p.CANDIDATE),'--candidate-seal',p.CANDIDATE_SHA])
        self.assertIs(p.frozen.evaluate,original)


if __name__=='__main__':unittest.main()
