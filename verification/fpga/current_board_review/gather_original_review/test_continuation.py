#!/usr/bin/env python3
"""Host regressions for missing startup paths and fast-finished control races."""
import copy
from pathlib import Path
import shutil
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import check_continuation as checker
import replay_continuation04 as replay


class Continuation(unittest.TestCase):
    def fixture(self, root):
        original = checker.CONTROL
        plan = replay.read(original / 'plan.json')
        plan['pins'] = {}
        replay.save(root / 'plan.json', plan)
        digest = replay.sha(root / 'plan.json')
        source = original / 'control/replay'
        folder = root / 'control/replay'
        case = folder / 'tests' / checker.NAMES[0]
        (case / 'work').mkdir(parents=True)
        old_case = source / 'tests' / checker.NAMES[0]
        for name in ('input.elf', 'console.log', 'commit_trace.csv', 'work/run.vcs.log'):
            shutil.copyfile(old_case / name, case / name)
        inputs = replay.read(old_case / 'inputs.json')
        inputs['binary']['path'] = str(case / 'input.elf')
        replay.save(case / 'inputs.json', inputs)
        command = replay.read(old_case / 'command.json')
        command['cwd'] = str(case / 'work')
        command['command'] = [a.replace(str(old_case), str(case)) for a in command['command']]
        replay.save(case / 'command.json', command)
        summary = replay.read(source / 'summary.json')
        summary[0]['artifact_dir'] = str(case)
        replay.save(folder / 'summary.json', summary)
        replay.save(folder / 'run.json', replay.read(source / 'run.json'))
        gate = replay.read(original / 'control/independent_gate.json')
        gate['plan_sha256'] = digest
        replay.save(root / 'control/independent_gate.json', gate)
        return digest, case

    def test_missing_path_and_fast_finished_control(self):
        with tempfile.TemporaryDirectory(prefix='host_race_', dir=replay.DATA) as tmp:
            root = Path(tmp)
            digest, _ = self.fixture(root)
            startup = root / 'control/actual_simv_confirmation.json'
            with patch.object(checker, 'CONTROL', root), patch.object(checker, 'CONTROL_HASH', digest):
                self.assertFalse(startup.exists())
                with self.assertRaises(FileNotFoundError):
                    replay.sealed.read(startup)
                self.assertEqual(checker.inherited_control(root, digest)['status'], 'PASS_TERMINAL_CONTROL')
                replay.save(startup, dict(status='NOT_CONFIRMED', reason='Real simv advancement not confirmed'))
                with self.assertRaisesRegex(ValueError, 'Startup confirmation missing'):
                    replay.require(replay.read(startup)['status'] == 'ADVANCING_1_SIMV',
                                   'Startup confirmation missing')
                accepted = checker.inherited_control(root, digest)
                self.assertEqual(accepted['status'], 'PASS_TERMINAL_CONTROL')
                self.assertFalse(accepted['rerun_control'])
                self.assertTrue(accepted['raw_artifacts_revalidated'])

    def test_failed_exit_or_oracle_never_inherits(self):
        with tempfile.TemporaryDirectory(prefix='host_veto_', dir=replay.DATA) as tmp:
            root = Path(tmp)
            digest, case = self.fixture(root)
            summary_file = root / 'control/replay/summary.json'
            summary = replay.read(summary_file)
            with patch.object(checker, 'CONTROL', root), patch.object(checker, 'CONTROL_HASH', digest):
                summary[0]['returncode'] = 1
                replay.save(summary_file, summary)
                with self.assertRaisesRegex(ValueError, 'not PASS/exit0'):
                    checker.inherited_control(root, digest)
                summary[0]['returncode'] = 0
                replay.save(summary_file, summary)
                log = case / 'console.log'
                log.write_text(log.read_text().replace('cases=1 errors=0', 'cases=1 errors=1'))
                with self.assertRaisesRegex(ValueError, 'RVV_PERMUTE_PASS'):
                    checker.inherited_control(root, digest)

    def test_progress_failure_retains_raw_samples(self):
        cgroup = Path('/proc/self/cgroup').read_text()
        simv = replay.read(replay.IMAGE / 'image.json')['simv']
        samples = [dict(pid=n, cpu_ticks=100, trace_bytes=8192, last_cycle=100,
                       executable=str(Path(simv).resolve()), cgroup=cgroup,
                       argv=[simv], cwd='/private') for n in (101,102)]
        after = copy.deepcopy(samples)
        for x in after:
            x.update(cpu_ticks=110, trace_bytes=16384, last_cycle=200)
        self.assertTrue(all(all(x.values()) for x in replay.progress_checks(samples, after, simv, cgroup)))
        after[0]['last_cycle'] = 100
        self.assertFalse(all(all(x.values()) for x in replay.progress_checks(samples, after, simv, cgroup)))
        class Proc:
            def __init__(self, n):
                self.name = str(n)
            def __truediv__(self, _):
                command = simv+'\0+COMMIT_TRACE='+str(replay.OUT / 'remaining7/replay/tests/x/commit_trace.csv')+'\0'
                return SimpleNamespace(read_bytes=lambda: command.encode())
        retained = []
        with patch.object(Path, 'glob', return_value=[Proc(101),Proc(102)]), \
             patch.object(replay.sealed, 'sample', side_effect=samples+after), \
             patch.object(replay.time, 'sleep'), \
             patch.object(replay, 'save', side_effect=lambda path, data: retained.append(data)):
            replay.confirm_startup(threading.Event())
        self.assertEqual(retained[0]['status'], 'NOT_CONFIRMED')
        self.assertEqual(retained[0]['samples'], [samples,after])
        self.assertTrue(retained[0]['raw_samples_retained'])
        self.assertFalse(retained[0]['checks'][0]['cycle_growing'])

    def test_sealed_inputs_and_real_control_unchanged(self):
        plan = replay.read(checker.CONTROL / 'plan.json')
        replay.pins_check(plan['pins'])
        inherited = checker.inherited_control()
        self.assertEqual(inherited['results'][0]['trace']['rows'], 9548)
        programs = replay.read(replay.DATA / 'soc01/programs.json')['programs']
        self.assertEqual(list(programs), checker.NAMES)
        for name, entry in programs.items():
            self.assertEqual(replay.sha(Path(entry['path'])), plan['pins'][entry['path']])
        self.assertEqual(replay.sha(replay.IMAGE / 'image.json'), replay.IMAGE_SHA)
        self.assertEqual(replay.read(checker.CONTROL / 'complete.json')['status'], 'NOT_ACCEPTED')
        self.assertFalse((checker.CONTROL / 'remaining7').exists())

    def test_independent_checker_recomputes_growth(self):
        simv = replay.read(replay.IMAGE / 'image.json')['simv']
        before = []
        for pid,name in zip((101,102), checker.NAMES[1:3]):
            case = replay.OUT / 'remaining7/replay/tests' / name
            before.append(dict(pid=pid, cpu_ticks=10, trace_bytes=8192, last_cycle=100,
                executable=str(Path(simv).resolve()), cgroup='/worker', cwd=str(case / 'work'),
                argv=[simv, '+TESTCASE='+name, '+PRELOAD='+str(case / 'input.elf'),
                      '+COMMIT_TRACE='+str(case / 'commit_trace.csv')]))
        after = copy.deepcopy(before)
        for x in after:
            x.update(cpu_ticks=20, trace_bytes=16384, last_cycle=200)
        record = dict(status='ADVANCING_2_SIMV', raw_samples_retained=True,
                      worker_cgroup='/worker', samples=[before,after], checks=[dict(ok=True)]*2)
        plan, worker = dict(image=str(replay.IMAGE)), dict(cgroup='/worker')
        checker.verify_progress(replay.OUT, plan, record, worker)
        after[0]['last_cycle'] = 100
        with self.assertRaisesRegex(ValueError, 'growth failed'):
            checker.verify_progress(replay.OUT, plan, record, worker)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Continuation)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    replay.save(replay.DATA / 'continuation_host.json', dict(status='PASS' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun, worker_sha256=replay.sha(Path(replay.__file__)),
        checker_sha256=replay.sha(Path(checker.__file__)), test_sha256=replay.sha(Path(__file__)),
        inherited_control_only=True, no_dut_launched=True))
    raise SystemExit(not result.wasSuccessful())
