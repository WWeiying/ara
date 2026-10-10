import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import admit_gap106_offline as m


class Contracts(unittest.TestCase):
    def record(self):
        return dict(status='GAP106_EXACT726_PLUS_ONE_CANDIDATE_NOT_ADMITTED',baseline=str(m.candidate.BASE),
            baseline_seal=m.candidate.BASE_SEAL,qualification=str(m.candidate.QUAL),qualification_seal=m.QUAL_SEAL,
            proposed_population=727,exact726_prefix=True,coverage_admitted=False,full_scalar_isa_verified=False,
            spike_custom_isa_pass=False,rtl_changed=False,simulations_started=False,raw_delta=m.EXPECTED_DELTA.copy(),
            output_pins={str(m.CANDIDATE/n):'a'*64 for n in m.PRODUCTS})

    def test_exact_candidate_contract(self):
        m.candidate_contract(self.record())

    def test_actual_candidate_bound_contract(self):
        record=m.life.read_bound(m.CANDIDATE/'candidate.json',m.CANDIDATE_SEAL)
        m.candidate_contract(record)

    def test_wrong_base_rejected(self):
        r=self.record();r['baseline_seal']='b'*64
        with self.assertRaises(ValueError):m.candidate_contract(r)

    def test_wrong_qualification_rejected(self):
        r=self.record();r['qualification_seal']='b'*64
        with self.assertRaises(ValueError):m.candidate_contract(r)

    def test_missing_product_rejected(self):
        r=self.record();r['output_pins'].pop(next(iter(r['output_pins'])))
        with self.assertRaises(ValueError):m.candidate_contract(r)

    def test_foreign_product_rejected(self):
        r=self.record();r['output_pins']['/foreign/combined-bits.json']='b'*64
        with self.assertRaises(ValueError):m.candidate_contract(r)

    def test_zero_or_old_gain_rejected(self):
        for delta in (dict(line=0,cond=0,branch=0,fsm=0),dict(line=0,cond=191,branch=0,fsm=0)):
            r=self.record();r['raw_delta']=delta
            with self.assertRaises(ValueError):m.candidate_contract(r)

    def test_full_scalar_or_spike_claim_rejected(self):
        for key in ('full_scalar_isa_verified','spike_custom_isa_pass'):
            r=self.record();r[key]=True
            with self.assertRaises(ValueError):m.candidate_contract(r)

    def test_already_admitted_candidate_rejected(self):
        r=self.record();r['coverage_admitted']=True
        with self.assertRaises(ValueError):m.candidate_contract(r)

    def test_seal_gate_before_replay_or_raw_collection(self):
        with patch.object(m.candidate.bitmap,'collect') as collect,patch.object(m.candidate.qualifier,'runtime') as replay:
            with self.assertRaises(ValueError):m.evaluate('bad',m.QUAL_SEAL,m.CANDIDATE_SEAL)
            collect.assert_not_called();replay.assert_not_called()

    def test_pin_conflict_cannot_overwrite_expected(self):
        with self.assertRaises(ValueError):m.life.merge_pins({'/source':'a'*64},{'/source':'b'*64})


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)/'formal727'
        self.record=self.out.with_name(self.out.name+'.prepared.json')
        self.outputs={'status.json':dict(coverage_admitted=True,aggregate_passed=727),'evidence-pins.json':{}}
        self.text='design\nunique-test\n'
        self.patches=[patch.object(m.life,'OUT',Path(self.tmp.name)),
                      patch.object(m,'evaluate',return_value=(self.outputs,self.text))]
        for p in self.patches:p.start();self.addCleanup(p.stop)

    def args(self,mode,seal=None):
        args=[mode,'--base-seal',m.candidate.BASE_SEAL,'--qualification-seal',m.QUAL_SEAL,
              '--candidate-seal',m.CANDIDATE_SEAL,'--output',str(self.out)]
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
        seal=self.prepare();self.outputs['status.json']['aggregate_passed']=728
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


if __name__=='__main__':unittest.main()
