import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('chain_profile', Path(__file__).with_name('profile.py'))
PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROFILE)


def fixture():
    trials = [dict(id=i, candidate=(0, 1, 1, 0)[i], errors=0,
                   admit=10, prep=20, execute=650, total=700) for i in range(4)]
    lines = []
    for trial in trials:
        for _ in range(64):
            p = dict.fromkeys(PROFILE.COUNTS, 0)
            p.update(seq=len([x for x in lines if x.startswith('[QBS_PERF]')]) + 1,
                     m=4, n=32, vlen=1024, lanes=4, success=1,
                     fault=0, validation_fault=0, read_fault=0, busy_cycles=10,
                     dot_active_cycles=4, pair_capacity=128, useful_pairs=128, tiles=1,
                     phase_setup_cycles=1, phase_compute_cycles=6, phase_overlap_cycles=3,
                     probe_compute_without_dot_issue_cycles=5)
            lines.append('[QBS_PERF] ' + ' '.join(f'{k}={v}' for k, v in p.items()))
        lines.append('M4_SUMS_QKV_TRIAL ' + ' '.join(f'{k}={v}' for k, v in trial.items()))
    return '\n'.join(lines), trials


class TestProfile(unittest.TestCase):
    def test_exclusive_accounting(self):
        text, trials = fixture()
        result = PROFILE.projection_profile(text, trials)
        self.assertEqual(sum(x['cycles'] for x in result['complete_slice_partition']), 700)
        self.assertEqual(result['counts_mean']['busy_cycles'], 640)
        self.assertEqual(result['compute_no_issue_per_tile'], 5)
        self.assertEqual(result['complete_slice_partition'][3]['cycles'], 10)

    def test_rejects_failed_or_duplicate_command(self):
        text, trials = fixture()
        for changed in (text.replace('success=1', 'success=0', 1),
                        text.replace('seq=2 ', 'seq=1 ', 1),
                        text.replace('busy_cycles=10 ', 'busy_cycles=11 ', 1)):
            with self.subTest(changed=changed[:100]), self.assertRaises(ValueError):
                PROFILE.projection_profile(changed, trials)

    def test_rejects_missing_or_extra_work(self):
        text, trials = fixture()
        lines = text.splitlines()
        for changed in ('\n'.join(lines[1:]), text + '\n' + lines[0]):
            with self.assertRaises(ValueError):
                PROFILE.projection_profile(changed, trials)

    def test_rejects_timing_and_compute_disagreement(self):
        text, trials = fixture()
        changed = copy.deepcopy(trials)
        changed[1]['total'] += 1
        with self.assertRaises(ValueError):
            PROFILE.projection_profile(text, changed)
        with self.assertRaises(ValueError):
            PROFILE.projection_profile(text.replace('probe_compute_without_dot_issue_cycles=5',
                                                    'probe_compute_without_dot_issue_cycles=6', 1), trials)

    def test_rejects_duplicate_fields(self):
        with self.assertRaises(ValueError):
            PROFILE.numeric_fields('X a=1 a=2', 'X ')

    def test_structure_is_logical_work_not_bus_measurement(self):
        result = PROFILE.attention_structure(2, 128, 20)
        self.assertEqual(result['output_update_read_write_bytes'], 40960)
        self.assertEqual(result['final_output_bytes'], 1024)
        self.assertEqual(result['q8_0_value_payload_bytes'], 2720)
        self.assertEqual(result['output_update_to_final_write_ratio'], 40)
        for geometry in ((0, 128, 20), (2, 127, 20), (9, 128, 20), (2, 128, 0)):
            with self.assertRaises(ValueError):
                PROFILE.attention_structure(*geometry)

    def test_board_ratios_use_totals_not_mean_speedups(self):
        cases = []
        for i in range(4):
            base = dict(prompt_eval_seconds=5.0, decode_eval_seconds=3.0,
                        inference_seconds=9.0 + i, host_elapsed_seconds=15.0 + i)
            candidate = {k: v / 2 for k, v in base.items()}
            cases.append(dict(name=str(i), prompt_tokens=1, generated_tokens=1,
                              metrics=dict(baseline=base, candidate=candidate)))
        result = PROFILE.board_timing(cases)
        self.assertEqual(result['aggregate_speedups']['inference_seconds'], 2)
        self.assertEqual(result['outside_inference_seconds']['candidate'], 12)
        bad = copy.deepcopy(cases)
        bad[0]['metrics']['candidate']['host_elapsed_seconds'] = 1
        with self.assertRaises(ValueError):
            PROFILE.board_timing(bad)
        with self.assertRaises(ValueError):
            PROFILE.board_timing(cases + [cases[0]])


if __name__ == '__main__':
    unittest.main()
