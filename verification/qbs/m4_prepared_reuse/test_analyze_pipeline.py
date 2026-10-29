import copy
import unittest

from analyze_pipeline import analyze, COUNTS, PHASES


def fixture():
    lines, trials = [], []
    for i in range(4):
        trial = dict(id=i, reuse=(0,1,1,0)[i], admit=10, prep=20, execute=6400,
                     total=6430, hits=0, misses=0, stores=0, fcsr=17, vcsr=5, errors=0)
        trials.append(trial)
        for command in range(64):
            p = dict.fromkeys(COUNTS, 0)
            p.update(seq=i*64+command+1, m=4, n=32, vlen=1024, lanes=4,
                success=1, fault=0, validation_fault=0, read_fault=0,
                busy_cycles=100, phase_compute_cycles=100, tiles=1,
                dot_active_cycles=80, useful_pairs=2560, pair_capacity=2560,
                probe_compute_without_dot_issue_cycles=6)
            lines.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in p.items()))
        lines.append('M4_QKV_TRIAL '+' '.join(f'{k}={v}' for k,v in trial.items()))
    lines.append('M4_QKV_RESULT errors=0 trials=4 m=4 k=1536 outputs=8192 commands=256')
    return '\n'.join(lines), trials


class PipelineAnalysisTest(unittest.TestCase):
    def test_valid_and_estimate(self):
        text, trials = fixture()
        result = analyze(text, trials)
        self.assertEqual(result['trials'][0]['dot_issue_fraction_of_busy'], 0.8)
        self.assertEqual(result['trials'][0]['issued_pair_fill'], 1)
        self.assertEqual(result['optimized_pair']['compute_no_issue'], 768)
        self.assertAlmostEqual(result['optimized_pair']['idealized_compute_no_issue_removed_speedup'],
                               12860/(12860-768))

    def test_reject_inconsistent_evidence(self):
        text, trials = fixture()
        for old, new in (('seq=1 ', 'seq=2 '), ('m=4 ', 'm=2 '),
                         ('phase_compute_cycles=100', 'phase_compute_cycles=99'),
                         ('pair_capacity=2560', 'pair_capacity=2559'),
                         ('probe_fp_slot_blocked_cycles=0', 'probe_fp_slot_blocked_cycles=1'),
                         ('success=1', 'success=0'),
                         ('errors=0 trials=4', 'errors=1 trials=4')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                analyze(text.replace(old, new, 1), trials)
        altered = copy.deepcopy(trials)
        altered[0]['total'] += 1
        with self.assertRaises(ValueError):
            analyze(text, altered)
        with self.assertRaises(ValueError):
            analyze(text+'\n'+text, trials)
        with self.assertRaises(ValueError):
            analyze(text.rsplit('\n', 1)[0], trials)


if __name__ == '__main__':
    unittest.main()
