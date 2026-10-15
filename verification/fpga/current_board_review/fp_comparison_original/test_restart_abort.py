"""Software-only negative tests; real CSV validator, no DUT or invented oracle."""
import os
from pathlib import Path
import signal
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import replay_restart_abort as r


class AbortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.entry = r.read(r.old.PLAN / 'plan.json')['cases'][0]
        self.abort = r.AbortLatch()
        self.test = SimpleNamespace(name=self.entry['id'])
        self.result = SimpleNamespace(name=self.test.name, status='PASS', returncode=0,
                                      reason='', artifact_dir=self.root)
        text = '\n'.join(self.entry['pass_markers']) + '\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
        (self.root / 'console.log').write_text(text)
        target = next(x for x in self.entry['target_retirements'] if x['calls'])
        (self.root / 'commit_trace.csv').write_text('cycle,event,order,pc,insn,trap\n' + ''.join(
            f"{i},retire,{i},{target['pc']},{target['opcode']},0\n" for i in range(130)))
        value = self.result
        class Parent:
            def _run_test(self, test, image):
                return value
        self.parent = Parent

    def checked(self):
        return r.runner_class(self.parent, {self.test.name: self.entry}, self.abort)()

    def during_validation(self, checked, action):
        entered, released = threading.Event(), threading.Event()
        original = r.prior.csv.DictReader
        errors = []
        def rows(*args, **kwargs):
            for i, row in enumerate(original(*args, **kwargs)):
                if i == 64:
                    entered.set()
                    if not released.wait(5):
                        raise AssertionError('Abort blocked on expensive validation')
                yield row
        def cancel():
            try:
                if not entered.wait(5):
                    raise AssertionError('Actual CSV validation not entered')
                action()
            except BaseException as error:
                errors.append(error)
            finally:
                released.set()
        thread = threading.Thread(target=cancel)
        thread.start()
        try:
            with patch.object(r.prior.csv, 'DictReader', rows):
                result = checked._run_test(self.test, None)
        finally:
            thread.join(6)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(entered.is_set())
        return result

    def test_sealed05_bug_reproduced_during_real_csv(self):
        checked = r.prior.runner_class(self.parent, {self.test.name: self.entry})()
        checked.cancel_event = self.abort
        result = self.during_validation(checked, self.abort.set)
        self.assertTrue(self.abort.is_set())
        self.assertEqual((result.status, result.returncode), ('PASS', 0))
        self.assertEqual(r.read(self.root / 'architectural_trace_audit.json')['retired'], 130)

    def test_successor_cancel_during_real_csv(self):
        result = self.during_validation(self.checked(), self.abort.set)
        self.assertEqual(result.status, 'CANCELLED')
        self.assertTrue(self.abort.is_set())
        self.assertEqual(r.read(self.root / 'architectural_trace_audit.json')['retired'], 130)
        self.assertFalse(self.abort.publish(self.root / 'complete.json', {}, True))

    def frozen_runner_repro(self, successor):
        _, _, _, engine = r.old.identity()
        root, entry, result = self.root, self.entry, self.result
        class Fixture(engine.RegressionRunner):
            def prepare(self):
                self.output_root.mkdir(exist_ok=True)
                r.save(self.output_root / 'run.json', dict(status='PREPARED'))
            def build(self):
                return None
            def _run_test(self, test, image):
                return engine.TestResult(result.name, 'app', 'PASS', 0, 1.0, '', result.artifact_dir)
        if successor:
            cls = r.runner_class(Fixture, {self.test.name: entry}, self.abort)
        else:
            cls = r.prior.runner_class(Fixture, {self.test.name: entry})
        opts = engine.RunOptions(root, root / 'runner', 'default', 1, 1, False, False, False, None, True, None)
        instance = cls(opts, [self.test], [])
        instance.cancel_event = self.abort
        # Use the frozen executor, signal context and report writer. Only DUT
        # execution is replaced by a completed scalar-oracle fixture.
        class CallRun:
            def _run_test(self, test, image):
                return instance.run()[0]
        with self.abort.signals():
            row = self.during_validation(CallRun(), self.abort.set)
            self.assertIsNotNone(signal.getsignal(signal.SIGTERM))
        meta = r.read(opts.output_root / 'run.json')
        self.assertEqual(meta['status'], 'INTERRUPTED')
        self.assertEqual(meta['status_counts'], {'CANCELLED' if successor else 'PASS': 1})
        return row

    def test_frozen_run_old_pass_rows_but_interrupted(self):
        self.assertEqual(self.frozen_runner_repro(False).status, 'PASS')

    def test_frozen_run_successor_cancelled_and_interrupted(self):
        self.assertEqual(self.frozen_runner_repro(True).status, 'CANCELLED')

    def test_signal_during_real_csv(self):
        with self.abort.signals():
            result = self.during_validation(self.checked(), lambda: os.kill(os.getpid(), signal.SIGTERM))
        # _run_test masks signals in its executing thread; restored mask delivers
        # a deferred signal before terminal acceptance even if the row was PASS.
        self.assertTrue(self.abort.is_set())
        self.assertFalse(self.abort.publish(self.root / 'complete.json', {}, result.status == 'PASS'))

    def test_no_abort_positive_real_csv(self):
        self.assertEqual(self.checked()._run_test(self.test, None).status, 'PASS')
        self.assertFalse(self.abort.is_set())

    def test_preexisting_abort(self):
        self.abort.set()
        self.assertEqual(self.checked()._run_test(self.test, None).status, 'CANCELLED')

    def test_clear_forbidden(self):
        self.abort.set()
        with self.assertRaises(RuntimeError):
            self.abort.clear()
        self.assertTrue(self.abort.wait(0))

    def test_raw_failure_latches(self):
        with (self.root / 'console.log').open('a') as stream:
            stream.write('RVV_FP_COMPARE_DETAIL bit=84\n')
        self.assertEqual(self.checked()._run_test(self.test, None).status, 'FAIL')
        self.assertTrue(self.abort.is_set())

    def test_csv_exception_latches(self):
        (self.root / 'commit_trace.csv').write_text('broken\n')
        with self.assertRaises(AssertionError):
            self.checked()._run_test(self.test, None)
        self.assertTrue(self.abort.is_set())

    def test_log_exception_latches(self):
        (self.root / 'console.log').unlink()
        with self.assertRaises(FileNotFoundError):
            self.checked()._run_test(self.test, None)
        self.assertTrue(self.abort.is_set())

    def terminal_fixture(self):
        results = [SimpleNamespace(name=n, status='PASS', returncode=0, artifact_dir=self.root / n)
                   for n in sorted(r.old.NAMES)]
        r.save(self.root / 'run.json', dict(status='COMPLETE', status_counts={'PASS': 2}))
        r.save(self.root / 'summary.json', [dict(name=x.name, status=x.status, returncode=x.returncode,
                                              artifact_dir=str(x.artifact_dir)) for x in results])
        return results

    def test_complete_exact_two_positive(self):
        r.terminal_inputs(self.terminal_fixture(), self.root)

    def test_interrupted_pass_rows_rejected(self):
        rows = self.terminal_fixture()
        r.save(self.root / 'run.json', dict(status='INTERRUPTED', status_counts={'PASS': 2}))
        with self.assertRaises(ValueError):
            r.terminal_inputs(rows, self.root)

    def test_wrong_status_counts_rejected(self):
        rows = self.terminal_fixture()
        r.save(self.root / 'run.json', dict(status='COMPLETE', status_counts={'PASS': 1, 'CANCELLED': 1}))
        with self.assertRaises(ValueError):
            r.terminal_inputs(rows, self.root)

    def test_duplicate_summary_rejected(self):
        rows = self.terminal_fixture()
        summary = r.read(self.root / 'summary.json')
        r.save(self.root / 'summary.json', [summary[0], summary[0]])
        with self.assertRaises(ValueError):
            r.terminal_inputs(rows, self.root)

    def test_nonzero_summary_rejected(self):
        rows = self.terminal_fixture()
        summary = r.read(self.root / 'summary.json')
        summary[0]['returncode'] = 1
        r.save(self.root / 'summary.json', summary)
        with self.assertRaises(ValueError):
            r.terminal_inputs(rows, self.root)

    def test_missing_run_rejected(self):
        rows = self.terminal_fixture()
        (self.root / 'run.json').unlink()
        with self.assertRaises(FileNotFoundError):
            r.terminal_inputs(rows, self.root)

    def test_abort_after_terminal_input_validation(self):
        r.terminal_inputs(self.terminal_fixture(), self.root)
        self.abort.set()
        self.assertFalse(self.abort.publish(self.root / 'complete.json', {}, True))

    def test_abort_during_terminal_serialization(self):
        save = r.save
        def write(path, record):
            save(path, record)
            if path.name.endswith('.pass.tmp'):
                worker = threading.Thread(target=self.abort.set)
                worker.start()
                worker.join(2)
                self.assertFalse(worker.is_alive(), 'Serialization held the abort lock')
        with patch.object(r, 'save', write):
            self.assertFalse(self.abort.publish(self.root / 'complete.json', {}, True))
        self.assertEqual(r.read(self.root / 'complete.json')['status'], 'NOT_PASS')

    def test_terminal_is_atomic_and_single_use(self):
        self.assertTrue(self.abort.publish(self.root / 'complete.json', {}, True))
        self.assertFalse(list(self.root.glob('*.tmp')))
        with self.assertRaises(ValueError):
            self.abort.publish(self.root / 'complete.json', {}, True)

    def test_no_pass_if_ineligible(self):
        self.assertFalse(self.abort.publish(self.root / 'complete.json', {}, False))

    def test_pending_signal_veto(self):
        with self.abort.signals():
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, r.SIGNALS)
            try:
                os.kill(os.getpid(), signal.SIGTERM)
                self.assertFalse(self.abort.publish(self.root / 'complete.json', {}, True))
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)

    def test_process_identity_both_names(self):
        for comm, argv, expected in [('simv', b'/tmp/renamed\0', True),
                                    ('renamed', b'/tmp/simv\0args', True),
                                    ('renamed', b'simv\0', True),
                                    ('bash', b'/bin/bash\0/tmp/simv', False),
                                    ('simv-helper', b'/tmp/simv-helper\0', False),
                                    ('simv', b'', True), ('bash', b'', False)]:
            with self.subTest(comm=comm, argv=argv):
                self.assertEqual(r.process_is_simv(comm, argv), expected)

    def test_renamed_comm_scanned_and_capacity_charged(self):
        for pid in range(5):
            proc = self.root / str(pid)
            proc.mkdir()
            (proc / 'comm').write_text('changed-name\n')
            (proc / 'cmdline').write_bytes(b'/actual/path/simv\0+foo\0')
            (proc / 'cgroup').write_text('0::/external')
        live = r.scan_simv(self.root)
        self.assertEqual(len(live), 5)
        units = {n: 'ara-test-' + n + '.service' for n in (*r.old.QUOTAS, 'gather', 'final38')}
        with self.assertRaises(ValueError):
            r.old.resource_math(live, 32 * 1024**3, units)

    def test_pin_drift_rejected_without_helper(self):
        path = self.root / 'helper.py'
        path.write_text('original')
        pins = {str(path): r.sha(path)}
        r.verify(pins)
        path.write_text('changed')
        with self.assertRaises(ValueError):
            r.verify(pins)

    def test_loaded_helper_pin_required(self):
        modules = r.local_modules()
        self.assertIn(str(r.HELPER), modules)
        r.module_gate(modules)
        del modules[str(r.HELPER)]
        with self.assertRaises(ValueError):
            r.module_gate(modules)


if __name__ == '__main__':
    unittest.main()
