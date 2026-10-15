#!/usr/bin/env python3
"""Host-only source/pin and acceptance-negative tests, no DUT launch."""
import json
from pathlib import Path
import tempfile
import unittest

import check_successor as checker
import replay_successor04 as replay
from check_terminal import console_check
from prepare_successor import narrow, replacements


class Successor(unittest.TestCase):
    def test_exact_sources_and_pins(self):
        replay.pins_check(replay.read(replay.DATA / 'baseline_pins.json'))
        programs = replay.read(replay.DATA / 'soc01/programs.json')
        provenance = replay.integration.check(Path(programs['prepared']))
        self.assertEqual(programs['provenance_sha256'], replay.sha(Path(programs['prepared']) / 'provenance.json'))
        self.assertEqual(provenance['baseline_pins_sha256'], replay.sha(replay.DATA / 'baseline_pins.json'))
        self.assertEqual(list(programs['programs']), checker.NAMES)
        for case in provenance['cases']:
            name = case['id']
            source = (replay.HERE / 'prepared01' / name / 'case.c').read_text()
            target = (Path(programs['prepared']) / name / 'case.c').read_text()
            self.assertEqual(target, narrow(source, case['original_case']['selected_trial']['op']))
            for entry in ('operations.S', 'operations.h', 'scenario.c'):
                self.assertEqual((replay.HERE / 'prepared01' / name / 'original' / entry).read_bytes(),
                                 (Path(programs['prepared']) / name / 'original' / entry).read_bytes())
        reference = replay.read(replay.DATA / 'reference01/reference.json')
        self.assertEqual([x['name'] for x in reference['results']], checker.NAMES)
        self.assertTrue(all(x['status'] == 'PASS' and x['returncode'] == 0 and x['full_oracle_markers']
                            for x in reference['results']))

    def test_failure_and_count_veto(self):
        for name in checker.NAMES:
            sew = name.split('_')[1][1:]
            markers = [f'RVV_PERMUTE_PASS sew={sew} cases=1 errors=0',
                       'BOARD_CASE_PASS '+name, 'BOARD_REPLAY_PASS']
            text = '\n'.join(['BOARD_CASE_BEGIN '+name, *markers,
                               'Core Test *** SUCCESS *** (tohost = 0)'])
            console_check(text, name)
            self.assertTrue(replay.oracle(dict(pass_markers=markers), text))
            for token in ('RVV_PERMUTE_FAIL', 'RVV_PERMUTE_DETAIL', 'RVV_PERMUTE_CAPACITY_FAIL',
                          'BOARD_CASE_FAIL', 'BOARD_REPLAY_TRAP', 'BOARD_REPLAY_VLEN_FAIL',
                          'BOARD_REPLAY_SERVICE_FAIL', 'BOARD_REPLAY_MISMATCH', 'SKIP',
                          'Core Test *** FAILED ***', 'UVM_FATAL : 1', 'Fatal: assertion failed'):
                with self.assertRaises(ValueError):
                    console_check(text+'\n'+token, name)
                self.assertFalse(replay.oracle(dict(pass_markers=markers), text+'\n'+token))
            for broken in (text.replace('cases=1', 'cases=0'), text.replace('errors=0', 'errors=1'),
                           text+'\n'+markers[0], text.replace('(tohost = 0)', '(tohost = 1)')):
                with self.assertRaises(ValueError):
                    console_check(broken, name)

    def test_timeout_or_missing_control_never_accepts(self):
        with tempfile.TemporaryDirectory(prefix='host_checker_', dir=replay.DATA) as tmp:
            out = Path(tmp)
            plan = dict(names=checker.NAMES, jobs=2, timeout_per_case_s=300, retries=0,
                stages=[dict(name='control', cases=checker.NAMES[:1], jobs=1),
                        dict(name='remaining7', cases=checker.NAMES[1:], jobs=2)],
                pins={}, image=str(replay.IMAGE), programs=str(replay.DATA / 'soc01'))
            replay.save(out / 'plan.json', plan)
            folder = out / 'control/replay'
            folder.mkdir(parents=True)
            replay.save(folder / 'summary.json', [dict(name=checker.NAMES[0], status='TIMEOUT', returncode=None)])
            run = dict(status='COMPLETE', completed_at=1, tests=checker.NAMES[:1], jobs=1,
                simv=replay.read(replay.IMAGE / 'image.json')['simv'], status_counts={'TIMEOUT':1})
            replay.save(folder / 'run.json', run)
            with self.assertRaisesRegex(ValueError, 'not all COMPLETE/PASS'):
                checker.validate_stage(out, replay.sha(out / 'plan.json'), 'control')
            run['status_counts'] = {'PASS':1}
            replay.save(folder / 'run.json', run)
            replay.save(folder / 'summary.json', [])
            with self.assertRaisesRegex(ValueError, 'membership'):
                checker.validate_stage(out, replay.sha(out / 'plan.json'), 'control')


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Successor)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    replay.save(replay.DATA / 'checker_host.json', dict(status='PASS' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun, worker_sha256=replay.sha(Path(replay.__file__)),
        checker_sha256=replay.sha(Path(checker.__file__)), test_sha256=replay.sha(Path(__file__))))
    raise SystemExit(not result.wasSuccessful())
