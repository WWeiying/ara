"""Host-only typed receipt and review rejection; no producer build is called."""
import argparse
import copy
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as w
import admission as a


def receipt():
    return dict(schema='quant_field_copy_pair_prepare_v1', state='GNU_PAIR_STATIC_PASS_NOT_EXECUTED',
        versions=w.REVISIONS, post_pins_match=True, rebuilt_object_count=3, reused_object_count=14,
        numerical_execution_checked=False, simulations_launched=0, performance_claim=False,
        historical_timing_reused=False, workload=dict(kind='q4_0', value_kind='q8_0',
            trial_order=[0, 1, 2, 2, 1, 0], trials=6, outputs_per_trial=768, total_outputs=4608,
            expected_commands=16, heads=6, head_dim=128, visible_tokens=128, kv_head=0,
            key_token_stride=144, value_token_stride=272, mapping_timed=True, admission_timed=True,
            gather_timed=True, workspace_bytes=13120, rvv_value_decode=True, rvv_baseline_decode=True,
            original_checks_preserved=True, timeout_seconds=10800))


class AdmissionTests(unittest.TestCase):
    def test_exact_preparation_workload_flags(self):
        a.receipt_flags(receipt())

    def test_published_native_producer_contract_no_process(self):
        builder = w.PAIR/'prepare/build.py'
        if not builder.exists(): self.skipTest('Preparation builder not published')
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('no producer execution')):
            producer = w.load('field_pair_native_contract_test', builder, w.s.digest(builder))
            r = receipt()
            r.update(workload=producer.WORKLOAD, versions=producer.VERSIONS)
            a.receipt_flags(r)
        self.assertEqual(producer.VERSIONS, w.REVISIONS)

    def test_receipt_types_revision_and_scope_mutations_reject(self):
        changes = [('state', 'PASS'), ('schema', 'old'), ('post_pins_match', 1),
            ('rebuilt_object_count', 2), ('reused_object_count', 15), ('simulations_launched', 1),
            ('numerical_execution_checked', True), ('performance_claim', True),
            ('historical_timing_reused', True), ('versions', dict(w.REVISIONS, baseline='0'*40))]
        for key, value in changes:
            r = receipt(); r[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): a.receipt_flags(r)

    def test_full_attention_and_original_checks_cannot_be_reduced(self):
        changes = [('trials', 3), ('total_outputs', 2304), ('outputs_per_trial', 767),
            ('trial_order', [0, 1, 2]), ('expected_commands', 8), ('heads', 1), ('head_dim', 64),
            ('visible_tokens', 32), ('mapping_timed', False), ('admission_timed', False),
            ('gather_timed', False), ('original_checks_preserved', False), ('timeout_seconds', 10801),
            ('rvv_value_decode', False), ('key_token_stride', 72), ('value_token_stride', 136)]
        for key, value in changes:
            r = receipt(); r['workload'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): a.receipt_flags(r)

    def test_parent_hash_rejects_before_receipt_or_producer_load(self):
        with tempfile.TemporaryDirectory() as d:
            review = Path(d)/'review.json'; review.write_text('not json')
            with patch.object(w, 'load', side_effect=AssertionError('must not import producer')):
                with self.assertRaisesRegex(ValueError, 'Parent review SHA'):
                    a.prepare_inputs(argparse.Namespace(review=review, review_sha256='0'*64))


if __name__ == '__main__':
    unittest.main()
