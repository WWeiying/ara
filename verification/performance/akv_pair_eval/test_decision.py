import importlib.util
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pair_decision', Path(__file__).with_name('decision.py'))
decision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decision)


class TestDecision(unittest.TestCase):
    def test_real_reduction_and_sample_spread(self):
        result = decision.effect([1000, 700, 710, 1010])
        self.assertAlmostEqual(result['speedup'], 1005/705)
        self.assertTrue(result['all_paired_samples_faster'])
        self.assertTrue(result['improvement_exceeds_arm_spread'])

    def test_positive_mean_is_not_enough(self):
        result = decision.effect([1000, 800, 1100, 1000])
        self.assertGreater(result['cycle_reduction'], 0)
        self.assertFalse(result['all_paired_samples_faster'])
        self.assertFalse(result['improvement_exceeds_arm_spread'])

    def test_regression_is_not_promoted(self):
        result = decision.effect([1000, 1100, 1110, 1010])
        self.assertLess(result['cycle_reduction'], 0)
        self.assertFalse(result['all_paired_samples_faster'])

    def test_no_partial_or_approximate_cycles(self):
        for value in ([1, 2, 3], [1, 2, 3, 0], [1, 2, 3, 4.0], [1, 2, 3, True]):
            with self.assertRaises(ValueError):
                decision.effect(value)

    def fixture(self, root, kind):
        directory = root/kind
        (directory/'work').mkdir(parents=True)
        paths = [directory/'input', directory/'image', directory/'work/run.vcs.log',
                 directory/'work/vector_trace.csv']
        for p in paths:
            p.write_text(p.name)
        pins = {str(paths[0]): decision.sha(paths[0])}
        (directory/'source-pins.json').write_text(json.dumps(pins))
        counts = [1046, 237, 237, 1046] if kind == 'qwen3_abba' else [209, 92, 92, 209]
        measured = dict(state='PASS', order=[0, 1, 1, 0],
                        measured_total_cycles=[1000, 700, 710, 1010],
                        work=dict(per_call_commands=counts))
        vector = dict(per_call_commands=counts)
        if kind == 'boundary':
            measured = dict(state='PASS', cases=4, complete_calls=12, native_commands=3680)
            vector = dict(native_commands=3680, ordered_signatures_checked=True)
        proof = dict(status='PASS', issues=[], elf_sha256='elf',
                     log_sha256=decision.sha(paths[2]), vector_trace_sha256=decision.sha(paths[3]))
        proofpath = directory/'work/uvm_result.json'
        proofpath.write_text(json.dumps(proof))
        result = dict(state='PASS', kind=kind, post_pins_match=True,
                      independent_protocol_checked=True, hardware_changed=False, whole_model=False,
                      performance_measured=kind != 'boundary', source_pins_sha256=decision.sha(directory/'source-pins.json'),
                      artifacts={str(p): decision.sha(p) for p in [*paths[1:], proofpath]},
                      measured=measured, vector_command_work=vector,
                      soc_build=str(directory), build=str(directory), configuration=dict(lanes=4),
                      image_sha256=decision.sha(paths[1]), software_sha256='elf')
        (directory/'result.json').write_text(json.dumps(result))
        expected_measured, expected_vector = copy.deepcopy(measured), copy.deepcopy(vector)
        checker = SimpleNamespace(check_run=lambda *_: copy.deepcopy(expected_measured),
                                  check_vector_workcounts=lambda *_: copy.deepcopy(expected_vector))
        return directory, result, checker

    def test_receipts_rebind_raw_evidence_and_reject_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory, original, checker = self.fixture(root, 'qwen3_abba')
            with patch.object(decision.owner, 'checked_soc', return_value=(dict(
                    configuration=original['configuration'], simv=str(directory/'image')), {})), \
                 patch.object(decision.owner, 'checked_software', return_value=(dict(elf_sha256='elf'), {})), \
                 patch.object(decision.owner, 'load_checker', return_value=(None, checker)):
                self.assertEqual(decision.checked_receipt(directory, 'qwen3_abba'), original)
                for field, value in [('state', 'FAIL'), ('kind', 'regression'),
                                     ('post_pins_match', False), ('image_sha256', 'bad')]:
                    bad = copy.deepcopy(original)
                    bad[field] = value
                    (directory/'result.json').write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):
                        decision.checked_receipt(directory, 'qwen3_abba')
                bad = copy.deepcopy(original)
                bad['measured']['measured_total_cycles'][1] = 1
                (directory/'result.json').write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError, 'recomputed'):
                    decision.checked_receipt(directory, 'qwen3_abba')
                (directory/'result.json').write_text(json.dumps(original))
                (directory/'work/run.vcs.log').write_text('changed')
                with self.assertRaisesRegex(ValueError, 'artifact changed'):
                    decision.checked_receipt(directory, 'qwen3_abba')

    def test_boundary_work_is_recomputed_not_just_nonempty(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory, result, checker = self.fixture(Path(tmp), 'boundary')
            result['vector_command_work']['native_commands'] = 1
            (directory/'result.json').write_text(json.dumps(result))
            with patch.object(decision.owner, 'checked_soc', return_value=(dict(
                    configuration=result['configuration'], simv=str(directory/'image')), {})), \
                 patch.object(decision.owner, 'checked_software', return_value=(dict(elf_sha256='elf'), {})), \
                 patch.object(decision.owner, 'load_checker', return_value=(None, checker)):
                with self.assertRaisesRegex(ValueError, 'recomputed'):
                    decision.checked_receipt(directory, 'boundary')

    def test_decision_threshold_five_percent_and_image_consistency(self):
        with tempfile.TemporaryDirectory() as tmp:
            triples = [self.fixture(Path(tmp), k) for k in ('qwen3_abba', 'regression', 'boundary')]
            results = [r for _, r, _ in triples]
            results[0]['measured']['measured_total_cycles'] = [1000, 950, 950, 1000]
            with patch.object(decision, 'checked_receipt', side_effect=results):
                self.assertTrue(decision.decide(*[p for p, _, _ in triples])[
                    'candidate_eligible_for_call_local_integration'])
            results[1]['image_sha256'] = 'different'
            with patch.object(decision, 'checked_receipt', side_effect=results):
                with self.assertRaisesRegex(ValueError, 'Different RTL images'):
                    decision.decide(*[p for p, _, _ in triples])


if __name__ == '__main__':
    unittest.main()
