import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import admit_gap110_offline as m

DIRECTORY = m.CANDIDATE
QSEAL, CSEAL, CFGSEAL = m.candidate.QUAL_SEAL, 'b'*64, m.candidate.CONFIG_SEAL
DELTA = dict(line=1,cond=1,branch=0,fsm=0)


class Contracts(unittest.TestCase):
    def record(self):
        return dict(status='GAP110_EXPLICIT_BASE_PLUS_ONE_CANDIDATE_NOT_ADMITTED',baseline=str(m.BASE),
            baseline_seal=m.BASE_SEAL,qualification=str(m.candidate.QUAL),qualification_seal=QSEAL,
            baseline_population=733,proposed_population=734,exact_baseline_prefix=True,
            config=str(m.CONFIG),config_seal=CFGSEAL,coverage_admitted=False,full_scalar_isa_verified=False,
            spike_custom_isa_pass=False,rtl_changed=False,simulations_started=False,raw_delta=DELTA.copy(),
            output_pins={str(DIRECTORY/n):'a'*64 for n in m.PRODUCTS})

    def test_exact_candidate_contract(self):
        m.candidate_contract(self.record(),DIRECTORY,QSEAL,CFGSEAL)

    def test_wrong_base_rejected(self):
        r=self.record();r['baseline_seal']='b'*64
        with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_wrong_qualification_rejected(self):
        r=self.record();r['qualification_seal']='c'*64
        with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_wrong_population_prefix_or_config_rejected(self):
        for key,value in (('baseline_population',727),('proposed_population',733),
                          ('exact_baseline_prefix',False),('config_seal','b'*64)):
            r=self.record();r[key]=value
            with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_missing_product_rejected(self):
        r=self.record();r['output_pins'].pop(next(iter(r['output_pins'])))
        with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_foreign_product_rejected(self):
        r=self.record();r['output_pins']['/foreign/combined-bits.json']='b'*64
        with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_zero_or_old_gain_rejected(self):
        for delta in (dict(line=0,cond=0,branch=0,fsm=0),dict(line=-1,cond=1,branch=0,fsm=0)):
            r=self.record();r['raw_delta']=delta
            with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_full_scalar_or_spike_claim_rejected(self):
        for key in ('full_scalar_isa_verified','spike_custom_isa_pass'):
            r=self.record();r[key]=True
            with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_already_admitted_candidate_rejected(self):
        r=self.record();r['coverage_admitted']=True
        with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_seal_gate_before_replay_or_raw_collection(self):
        with patch.object(m.candidate.bitmap,'collect') as collect,patch.object(m.candidate.qualifier,'runtime') as replay:
            with self.assertRaises(ValueError):m.evaluate('bad',QSEAL,CSEAL,DIRECTORY,CFGSEAL)
            collect.assert_not_called();replay.assert_not_called()

    def test_pin_conflict_cannot_overwrite_expected(self):
        with self.assertRaises(ValueError):m.life.merge_pins({'/source':'a'*64},{'/source':'b'*64})


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)/'formal734'
        self.record=self.out.with_name(self.out.name+'.prepared.json')
        self.outputs={'status.json':dict(coverage_admitted=True,aggregate_passed=734),
                      'raw-delta.json':dict(metrics=DELTA), 'evidence-pins.json':{}}
        self.text='design\nunique-test\n'
        self.patches=[patch.object(m.life,'OUT',Path(self.tmp.name)),
                      patch.object(m,'evaluate',return_value=(self.outputs,self.text))]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def args(self,mode,seal=None):
        args=[mode,'--base-seal',m.BASE_SEAL,'--qualification-seal',QSEAL,'--config-seal',CFGSEAL,
              '--candidate',str(DIRECTORY),'--candidate-seal',CSEAL,'--output',str(self.out)]
        if seal:args+=['--seal',seal]
        return args

    def prepare(self):
        m.main(self.args('prepare'));return m.life.digest(self.record)

    def test_prepare_only_no_formal_output(self):
        self.prepare();self.assertTrue(self.record.is_file());self.assertFalse(self.out.exists())

    def test_prepare_cannot_overwrite(self):
        seal=self.prepare()
        with self.assertRaises(ValueError):self.prepare()
        self.assertEqual(m.life.digest(self.record),seal)

    def test_admit_needs_external_seal(self):
        with self.assertRaises(ValueError):m.main(self.args('admit'))
        self.assertFalse(self.out.exists())

    def test_wrong_external_seal_no_output(self):
        self.prepare()
        with self.assertRaises(ValueError):m.main(self.args('admit','a'*64))
        self.assertFalse(self.out.exists())

    def test_proposal_output_mutation_rejected(self):
        seal=self.prepare();self.outputs['status.json']['aggregate_passed']=735
        with self.assertRaises(ValueError):m.main(self.args('admit',seal))
        self.assertFalse(self.out.exists())

    def test_authorized_write_and_independent_verify(self):
        seal=self.prepare();m.main(self.args('admit',seal))
        formal=self.out/'admission-manifest.json';formal_seal=m.life.digest(formal)
        self.assertTrue(json.loads((self.out/'status.json').read_bytes())['coverage_admitted'])
        m.main(self.args('verify',formal_seal))

    def test_verify_rejects_mutated_output(self):
        seal=self.prepare();m.main(self.args('admit',seal))
        formal_seal=m.life.digest(self.out/'admission-manifest.json')
        (self.out/'status.json').write_text('{}')
        with self.assertRaises(ValueError):m.main(self.args('verify',formal_seal))

    def test_admit_cannot_overwrite_formal_directory(self):
        seal=self.prepare();m.main(self.args('admit',seal))
        with self.assertRaises(ValueError):m.main(self.args('admit',seal))


class DynamicSeals(unittest.TestCase):
    def test_candidate_seal_malformed_rejected_before_runtime(self):
        with patch.object(m.life,'read_bound') as read,patch.object(m.candidate.qualifier,'runtime') as replay:
            with self.assertRaises(ValueError):m.evaluate(m.BASE_SEAL,QSEAL,'bad',DIRECTORY,CFGSEAL)
            read.assert_not_called();replay.assert_not_called()

    def test_measured_delta_not_hardcoded_prediction(self):
        r=Contracts().record();r['raw_delta']=dict(line=2,cond=17,branch=3,fsm=0)
        m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

    def test_bool_negative_extra_metric_rejected(self):
        for delta in (dict(line=True,cond=1,branch=0,fsm=0),
                      dict(line=1,cond=1,branch=0,fsm=0,tgl=1),
                      dict(line=1,cond=-1,branch=0,fsm=0)):
            r=Contracts().record();r['raw_delta']=delta
            with self.assertRaises(ValueError):m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)

class SuccessorBinding(unittest.TestCase):
    def test_exact_parent_candidate_and_v2_qualifier(self):
        self.assertEqual(Path(m.candidate.qualifier.__file__).name,'qualify_gap110_native_v2.py')
        self.assertEqual(m.CANDIDATE.name,'gap110-raw-gain-733-parent-20261006-01')
        self.assertEqual(m.candidate.QUAL.name,'gap110-native-v2-qualified-parent-20261006-01')
        self.assertEqual(m.candidate.qualifier.RUN_PID,3280044)

    def test_foreign_candidate_cannot_be_used_even_with_seal(self):
        with patch.object(m.life,'read_bound') as read:
            with self.assertRaises(ValueError):
                m.evaluate(m.BASE_SEAL,QSEAL,CSEAL,DIRECTORY.with_name('foreign-candidate'),CFGSEAL)
            read.assert_not_called()

    def test_bounded_native_scope_no_full_isa(self):
        r=Contracts().record();r['raw_delta']=dict(line=0,cond=26,branch=0,fsm=0)
        m.candidate_contract(r,DIRECTORY,QSEAL,CFGSEAL)
        self.assertFalse(r['coverage_admitted'])
        self.assertFalse(r['full_scalar_isa_verified'])
        self.assertFalse(r['spike_custom_isa_pass'])

if __name__=='__main__':unittest.main()




