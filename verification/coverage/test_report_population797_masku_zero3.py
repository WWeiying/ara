import copy
import csv
import io
import unittest
from pathlib import Path
from unittest.mock import patch

import report_population797_masku_zero3 as r


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous = r.life.read_bound(r.REPORT / 'config.json', r.CONFIG_SHA)
        cls.qualified = r.life.read_bound(r.REPORT / 'qualification.json', r.QUAL_SHA)
        cls.union = r.life.read_bound(r.UNION / 'config.json', r.UNION_SHA)

    def test_actual_completed797_q_and_original73scope(self):
        r.baseline_gate(self.previous, self.qualified)
        self.assertEqual(len(self.previous['hierarchy_roots']), 72)
        self.assertEqual(len(self.qualified['module_reports']['raw']), 73)
        self.assertEqual(len(self.qualified['output_pins']), 17)

    def test_missing_q_and_wrong_endpoint_before_output(self):
        reader = r.stable.Reader()
        with self.assertRaises(ValueError): r.approved(reader, r.handoff.OLD_BASE / 'admission-manifest.json', r.BASE_SHA)
        with patch.object(reader, 'read', side_effect=FileNotFoundError('qualification.json')):
            with self.assertRaises(FileNotFoundError): r.approved(reader, r.BASE, r.BASE_SHA)

    def test_baseline_negative_seal_population_pins_and_acceptance(self):
        for key, value in [('status', 'PREPARED'), ('config_seal', '0' * 64), ('admission_seal', '0' * 64),
                           ('population', 798), ('actual_selected_tests', 796), ('raw_reset_final_equal', False),
                           ('all_other_bits_protected', False), ('complete_approved_EL_bitmask_union', False)]:
            bad = copy.deepcopy(self.qualified)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): r.baseline_gate(self.previous, bad)
        bad = copy.deepcopy(self.qualified)
        bad['source_design_native_pins'].pop(next(iter(bad['source_design_native_pins'])))
        with self.assertRaises(ValueError): r.baseline_gate(self.previous, bad)

    def test_scope_expansion_or_missing_baseline_phase_rejected(self):
        previous = copy.deepcopy(self.previous)
        previous['hierarchy_roots'].append(dict(scope=r.handoff.q.SCOPE, name='i_masku_operands'))
        with self.assertRaises(ValueError): r.baseline_gate(previous, self.qualified)
        bad = copy.deepcopy(self.qualified)
        bad['module_reports'].pop('final')
        with self.assertRaises(ValueError): r.baseline_gate(self.previous, bad)

    def test_original_raw_reset_final_all_metrics_exact(self):
        reports = self.qualified['module_reports']
        r.baseline_metrics_gate(reports, reports)
        for stage in ('raw', 'reset', 'final'):
            for metric in r.stable.METRICS:
                bad = copy.deepcopy(reports)
                bad[stage]['ara_tb'][metric] = '0.00'
                with self.subTest(stage=stage, metric=metric), self.assertRaises(ValueError):
                    r.baseline_metrics_gate(bad, reports)

    def test_only_affected_score_toggle_may_change_applied(self):
        reports = self.qualified['module_reports']
        changed = copy.deepcopy(reports)
        for stage in ('applied', 'reloaded'):
            changed[stage]['ara_tb']['Toggle'] = '74.00'
            changed[stage]['ara_tb']['Score'] = '80.00'
        r.baseline_metrics_gate(changed, reports)
        for metric in ('Line', 'FSM', 'Condition', 'Branch'):
            bad = copy.deepcopy(changed)
            for stage in ('applied', 'reloaded'): bad[stage]['ara_tb'][metric] = '0.00'
            with self.assertRaises(ValueError): r.baseline_metrics_gate(bad, reports)
        unaffected = next(s for s in reports['applied'] if not r.handoff.q.SCOPE.startswith(s + '.') and s != r.handoff.q.SCOPE)
        bad = copy.deepcopy(changed)
        for stage in ('applied', 'reloaded'): bad[stage][unaffected]['Toggle'] = '0.00'
        with self.assertRaises(ValueError): r.baseline_metrics_gate(bad, reports)

    def test_raw2989_full_original_metrics_and_missing_rows(self):
        blob = (r.REPORT / 'raw.csv').read_bytes()
        original = r.raw_metrics(blob)
        self.assertEqual(len(original), 2989)
        parsed = csv.DictReader(io.StringIO(blob.decode()))
        rows, fields = list(parsed), parsed.fieldnames
        rows[0]['Toggle'] = '0.00'
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
        self.assertNotEqual(r.raw_metrics(stream.getvalue().encode()), original)
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows[:-1])
        with self.assertRaises(ValueError): r.raw_metrics(stream.getvalue().encode())

    def test_actual_completed_baseline_full_native_read_no_EDA(self):
        reader = r.stable.Reader()
        config, qualified, text, pins = r.baseline(reader)
        self.assertEqual(config, self.previous)
        self.assertEqual(qualified, self.qualified)
        self.assertEqual(text, (r.handoff.REPORT796 / 'combined.el').read_text())
        self.assertTrue(all(pins.get(p) == sha for p, sha in self.previous['pins'].items()))

    def test_actual_successor_full797_raw_zero_exact_EL_and_pins_no_EDA(self):
        reader = r.stable.Reader()
        with patch.object(r.engine, 'run', side_effect=AssertionError('No EDA')):
            source, pins, text, bits, chain, activity = r.approved(reader, r.BASE, r.BASE_SHA)
            reader.finish(r.stable.merge(pins, r.dependencies()))
        self.assertEqual(source['input_ledger'], self.previous['input_ledger'])
        self.assertEqual(source['hierarchy_roots'], self.previous['hierarchy_roots'])
        self.assertEqual(source['expected_selected'], self.previous['expected_selected'])
        self.assertEqual(source['tool_identity'], self.previous['tool_identity'])
        self.assertEqual(chain, self.previous['genealogy'])
        self.assertEqual(text, (r.UNION / 'combined.el').read_text())
        self.assertEqual(len(bits['tests']), 797)
        self.assertEqual(activity['baseline797_qualification_sha256'], r.QUAL_SHA)
        self.assertTrue(activity['MASKU_full797_suffix_zero']['full797_zero'])
        self.assertTrue(activity['MASKU_full797_suffix_zero']['suffix_raw_zero'])
        self.assertEqual(activity['EL_additions']['toggle_direction_members'], 1536)
        self.assertTrue(all(pins.get(p) == sha for p, sha in self.previous['pins'].items()))
        self.assertTrue(all(pins.get(p) == sha for p, sha in self.qualified['output_pins'].items()))

    def test_union_handoff_raw_flag_or_membership_drift_rejected(self):
        for mode in ('flag', 'membership', 'raw', 'strict', 'protected'):
            bad = copy.deepcopy(self.union)
            if mode == 'flag': bad['population_application'] = True
            elif mode == 'membership': bad['input_ledger'][-1] = bad['input_ledger'][-2]
            elif mode == 'raw': bad['raw_zero']['suffix_raw_zero'] = False
            elif mode == 'strict': bad['strict_MASKU_receipt_sha256'] = '0' * 64
            else: bad['protected_complement']['retained_other_objects'] = 983
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                r.union_contract(bad, self.previous, {}, '', '', '', '')

    def test_frozen_engine_only_exact_anchors_and_baseline_verify_gate(self):
        prepare, check, verify, run = r.context()
        self.assertIs(check.__globals__['approved'], r.approved)
        self.assertIs(run.__globals__['check'], check)
        self.assertIs(run.__globals__['verify'], verify)
        self.assertIs(verify.__globals__['compare_baseline_native'], r.compare_baseline_native)
        self.assertIn('new_exclusions_added', str(prepare.__code__.co_consts))
        self.assertEqual(len(r.stable.STAGES), 5)
        self.assertTrue(all(r.dependencies().get(p) == sha for p, sha in r.inherited.dependencies().items()))


if __name__ == '__main__': unittest.main()
