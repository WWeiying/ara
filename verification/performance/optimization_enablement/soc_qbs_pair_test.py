import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import soc_qbs_pair as p


def proof(mode, totals):
    return dict(state='PASS', outputs_bit_exact=1024, command_count=8, trials=[dict(
        id=i, mode=mode, status=0, commands=4, context=0, flags=3 | seed,
        expected_flags=3 | seed, q8_bad=0, output_bad=0, guards_bad=0, total=t)
        for i, (seed, t) in enumerate(zip((0, 8), totals))])


class PairTests(unittest.TestCase):
    def test_same_mode_per_trial_only(self):
        for name, mode in (('qbs_m4', 4), ('qbs_m8', 8)):
            rows = p.compare_trials(name, proof(mode, [100, 200]), proof(mode, [101, 190]))
            self.assertEqual([r['delta'] for r in rows], [1, -10])
            self.assertEqual([r['regression'] for r in rows], [True, False])
            self.assertEqual([r['trial'] for r in rows], [0, 1])
            self.assertTrue(all(r['mode'] == mode and r['case'] == name for r in rows))

    def test_cross_modes_seeds_and_work_rejected(self):
        good = proof(4, [100, 200])
        for field in ('id', 'mode', 'commands', 'flags', 'expected_flags', 'q8_bad', 'output_bad', 'guards_bad'):
            bad = copy.deepcopy(good); bad['trials'][0][field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError): p.compare_trials('qbs_m4', good, bad)
        with self.assertRaises(ValueError): p.compare_trials('qbs_m4', good, proof(8, [100, 200]))

    def test_incomplete_and_invalid_cycles_rejected(self):
        for field, value in (('state', 'FAIL'), ('outputs_bit_exact', 0), ('command_count', 7), ('trials', [])):
            bad = proof(4, [100, 200]); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): p.compare_trials('qbs_m4', proof(4, [100, 200]), bad)
        for t in (0, -1, 1.5, True):
            with self.subTest(total=t), self.assertRaises(ValueError): p.compare_trials('qbs_m4', proof(4, [100, 200]), proof(4, [t, 200]))

    def test_main_fail_never_admitted(self):
        runs = (('candidate', 'a'), ('baseline', 'b'))
        good = dict(state='SOC_COMBINATION_CHECKED', post_pins_match=True, source_pins_sha256=p.MAIN_REVIEW,
                    completed=[dict(arm=arm, case=name, state='PASS') for arm, name in runs])
        p.main_verdict(good, runs)
        for field, value in (('state', 'FAIL'), ('state', 'RUNNING'), ('post_pins_match', False),
                             ('completed', []), ('completed', good['completed'] * 2), ('source_pins_sha256', '0'*64)):
            bad = dict(good); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): p.main_verdict(bad, runs)

    def test_pidfd_is_single_blocking_wait_not_polling(self):
        with patch.object(p.os, 'pidfd_open', return_value=77) as opened, patch.object(p.os, 'close') as closed, \
             patch.object(p.Path, 'read_text', return_value='0::/unit.service\n'), \
             patch.object(p.select, 'select', return_value=([77], [], [])) as waited:
            p.wait_main_exit(dict(main_pid=123, unit='unit.service'), 100)
            opened.assert_called_once_with(123)
            waited.assert_called_once_with([77], [], [], 100)
            closed.assert_called_once_with(77)

    def test_exited_pid_and_wrong_owner(self):
        with patch.object(p.os, 'pidfd_open', side_effect=ProcessLookupError):
            p.wait_main_exit(dict(main_pid=123, unit='unit.service'), 1)
        with patch.object(p.os, 'pidfd_open', return_value=77), patch.object(p.os, 'close'), \
             patch.object(p.Path, 'read_text', return_value='0::/other.service\n'):
            with self.assertRaises(ValueError): p.wait_main_exit(dict(main_pid=123, unit='unit.service'), 1)

    def test_output_scope(self):
        self.assertEqual(p.output(p.OUT/'enablement_soc_qbs_pair_test'), p.OUT/'enablement_soc_qbs_pair_test')
        for path in (Path('/tmp/enablement_soc_qbs_pair_test'), p.OUT/'enablement_soc_campaign_test'):
            with self.assertRaises(ValueError): p.output(path)


if __name__ == '__main__': unittest.main()
