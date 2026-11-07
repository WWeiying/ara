#!/usr/bin/env python3
"""Host admission, negative perturbation, nesting and mandatory raw-replay checks."""
from copy import deepcopy
import unittest

import collect_attention_phase as c
from check_output_phase import check
from test_output_phase import fixture


class AttentionCollectionTests(unittest.TestCase):
    def test_worker_admission(self):
        original=c.read(c.WORKER/'result.json');c.admit_worker(original)
        for key,value in [('state','FAIL'),('child_pid',1),('post_pins_match',False),('independent_protocol_checked',False),
                          ('quantitative_phase_fractions_allowed',False),('whole_model',True),('optimization_speedup_claim',True),
                          ('exact_elf_spike_executed',True),('elf_sha256','0'*64)]:
            row=deepcopy(original);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.admit_worker(row)

    def test_build_admission(self):
        original=c.read(c.BUILD/'build.json');c.admit_build(original)
        for key,value in [('heads',2),('order',[0,1,0,1]),('rebuilt_objects',1),('reused_objects',17),
                          ('binding_nested_in_qk',False),('internal_timestamps_per_probed_call',44)]:
            row=deepcopy(original);row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.admit_build(row)

    def test_mandatory_raw_numerical_replay(self):
        text,golden=fixture();worker=dict(measured=check(text,golden))
        measured,summary=c.numerical_replay(text,golden,worker)
        self.assertEqual(measured,worker['measured']);self.assertTrue(summary['absolute_each_pair_and_aggregate_below_five_percent'])
        for raw in (text.replace('vstart=0','vstart=1',1),text.replace('timer_reads=46','timer_reads=44',1),
                    text.replace('errors=0','errors=1',1),text.replace('OUTPUT_PHASE_SUITE_PASS','')):
            with self.assertRaises((ValueError,AssertionError)):c.numerical_replay(raw,golden,worker)
        forged=deepcopy(worker);forged['measured']['uninstrumented_cycles']+=1
        with self.assertRaises(ValueError):c.numerical_replay(text,golden,forged)

    def test_both_directions_and_exact_five_percent_rejected(self):
        text,golden=fixture()
        for value in (93000,107000,105000,95000):
            measured=check(text.replace('cycles=103000','cycles='+str(value)),golden)
            with self.subTest(cycles=value),self.assertRaises(ValueError):c.quantitative_summary(measured)

    def test_pair_gate_not_hidden_by_average(self):
        text,golden=fixture()
        raw=text.replace('cycles=103000','cycles=107000',1)
        raw=raw.replace('cycles=103000','cycles=93000',1)
        measured=check(raw,golden)
        self.assertEqual(measured['measured_perturbation'],0)
        with self.assertRaises(ValueError):c.quantitative_summary(measured)

    def test_nested_binding_not_additive(self):
        text,golden=fixture();measured=check(text,golden);summary=c.quantitative_summary(measured)
        self.assertFalse(summary['binding_nested_in_qk']['add_to_exclusive'])
        self.assertAlmostEqual(sum(r['fraction_of_probed_call'] for r in summary['exclusive_phases'].values())+
                               summary['unobserved']['fraction_of_probed_call'],1)
        bad=deepcopy(measured);bad['trials'][1]['exclusive_phase_cycles']+=bad['trials'][1]['phases']['binding_cycles']
        with self.assertRaises(ValueError):c.quantitative_summary(bad)

    def test_complete_protocol_replay_required(self):
        worker=c.read(c.WORKER/'result.json');original=c.read(c.WORKER/'work/uvm_result.json')
        c.protocol_agreement(original,original,worker)
        for key,value in [('status','FAIL'),('issues',['injected']),('contract_event_count',0),
                          ('elf_sha256','0'*64),('sim_image_sha256',{})]:
            bad=deepcopy(original);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.protocol_agreement(bad,original,worker)


if __name__=='__main__':unittest.main()
