"""Deterministic host-only reproduction of timeout/cancellation acceptance races."""
from contextlib import ExitStack
from pathlib import Path
import json
import tempfile
import threading
import os
import signal
import unittest
from unittest.mock import Mock, patch
import vcs_jobs8_successor02 as s


class SuccessorTests(unittest.TestCase):
    def group(self, trigger=None, clock_expired=False):
        with tempfile.TemporaryDirectory(prefix='host_successor_', dir=s.base.HERE) as temporary:
            out = Path(temporary)
            (out / 'groups').mkdir()
            group = 47
            source = s.base.reference_directory(group)
            cmd = s.base.command(out, group, True)
            image = dict(simv='/image/simv', files={'/image/simv': 'IMAGE'})
            artifact = out / 'groups/group47/run/tests/nf8_g47'
            image_json = s.base.IMAGE / 'image.json'
            summary = [dict(name='nf8_g47', status='PASS', returncode=0)]
            data = {
                source / 'status.json': dict(elf_sha256=dict(soc='ELF')),
                source / 'soc.symbols.json': {}, source / 'cases.json': [],
                out / 'ledgers/group47.json': [],
                artifact.parent.parent / 'summary.json': summary,
                artifact.parent.parent / 'run.json': dict(status='COMPLETE', tests=['nf8_g47'],
                    commit_trace=True, simv=image['simv'], invocation=cmd[2:]),
                artifact / 'inputs.json': dict(simv=dict(path=image['simv'], image_sha256=image['files']),
                    binary=dict(sha256='ELF', source=str(source / 'soc.elf'))),
                image_json: image,
            }
            abort = s.base.scheduler.Abort()
            timer = Mock()
            callback = []
            clock = [0.0]
            checker = Mock()
            checker.failure.side_effect = lambda error: dict(status='NF8_CSV_NOT_PASS', error=str(error))
            checker.finish.side_effect = lambda: finish()

            def finish():
                if trigger == 'timeout':
                    callback[0]()
                elif trigger == 'signal':
                    abort.stop(dict(signal=15))
                if clock_expired:
                    clock[0] = 2521.0
                return dict(status='NF8_CSV_ORACLE_PASS', trials=[188, 189, 190, 191])

            def timer_factory(delay, fn):
                callback.append(fn)
                return timer

            def fake_wait(*args):
                artifact.mkdir(parents=True)
                # A real fixture file is unnecessary; console reads are mocked below.
                return 0

            original_read_text = Path.read_text
            def read_text(path, *args, **kwargs):
                return 'NA_SV39_PASS\n' if path.name == 'console.log' else original_read_text(path, *args, **kwargs)

            original_terminal = s.GroupTerminal
            original_publish = s.atomic_publish
            injected = False
            def publish(path, result):
                nonlocal injected
                original_publish(path, result)
                if trigger == 'publish_signal' and not injected:
                    injected = True
                    abort.stop(dict(signal=15))
            with ExitStack() as stack:
                stack.enter_context(patch.object(s.base, 'read', side_effect=lambda p: data[p]))
                stack.enter_context(patch.object(s.base, 'sha', return_value='ELF'))
                stack.enter_context(patch.object(s.base.csv_oracle, 'Checker', return_value=checker))
                stack.enter_context(patch.object(s.base.live_tail, 'DirectoryEvents', return_value=Mock()))
                stack.enter_context(patch.object(s.base.live_tail, 'wait_append', side_effect=fake_wait))
                stack.enter_context(patch.object(s.subprocess, 'Popen', return_value=Mock(poll=lambda: 0)))
                stack.enter_context(patch.object(s.threading, 'Timer', side_effect=timer_factory))
                stack.enter_context(patch.object(s, 'GroupTerminal', side_effect=lambda a, f: original_terminal(a, f, lambda: clock[0])))
                stack.enter_context(patch.object(Path, 'read_text', read_text))
                stack.enter_context(patch.object(s, 'atomic_publish', side_effect=publish))
                result = s.group_worker(out, group, abort)
            saved = s.base.read(out / 'groups/group47/complete.json')
            firstfailure = (out / 'groups/group47/firstfailure.json').exists()
            timer.cancel.assert_called_once()
            timer.join.assert_called_once()
            return result, saved, abort, firstfailure

    def test_real_group_timeout_during_finish_rc_zero(self):
        result, saved, abort, evidence = self.group('timeout')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(saved['status'], 'FAIL')
        self.assertTrue(result['timed_out'] and evidence)
        self.assertIsNotNone(abort.reason)

    def test_real_group_signal_during_finish_rc_zero(self):
        result, saved, abort, evidence = self.group('signal')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(saved['status'], 'FAIL')
        self.assertEqual(abort.reason, dict(signal=15))
        self.assertTrue(evidence)

    def test_expired_deadline_without_scheduled_callback(self):
        result, saved, abort, evidence = self.group(clock_expired=True)
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['timed_out'] and evidence)

    def test_successful_group_control(self):
        result, saved, abort, evidence = self.group()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(saved['status'], 'PASS')
        self.assertIsNone(abort.reason)
        self.assertFalse(evidence)

    def test_real_group_publication_cancel_replaces_existing_pass(self):
        result, saved, abort, evidence = self.group('publish_signal')
        self.assertEqual(result['returncode'], 0)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(saved['status'], 'FAIL')
        self.assertEqual(abort.reason, dict(signal=15))
        self.assertTrue(evidence)

    def test_inflight_timeout_mutually_excludes_accept(self):
        abort = s.base.scheduler.Abort()
        entered = threading.Event()
        release = threading.Event()
        def fail(error):
            entered.set()
            if not release.wait(2):
                raise RuntimeError('host race synchronization expired')
            abort.stop(dict(timeout=True))
        terminal = s.GroupTerminal(abort, fail, lambda: 0)
        thread = threading.Thread(target=terminal.timeout)
        thread.start()
        self.assertTrue(entered.wait(2))
        release.set()
        with patch.object(s, 'atomic_publish') as save:
            with self.assertRaises(ValueError): terminal.accept(dict(status='PASS'), Path('/unused'))
            save.assert_not_called()
        thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_timer_after_committed_accept_is_stale(self):
        abort = s.base.scheduler.Abort()
        fail = Mock()
        terminal = s.GroupTerminal(abort, fail, lambda: 0)
        with patch.object(s, 'atomic_publish'):
            terminal.accept(dict(status='PASS'), Path('/unused'))
        terminal.timeout()
        fail.assert_not_called()
        self.assertIsNone(abort.reason)

    def test_cancellation_reentering_group_write(self):
        abort = s.base.scheduler.Abort()
        terminal = s.GroupTerminal(abort, Mock(), lambda: 0)
        with patch.object(s, 'atomic_publish', side_effect=lambda *args: abort.stop(dict(signal=15))):
            with self.assertRaises(ValueError): terminal.accept(dict(status='PASS'), Path('/unused'))

    def aggregate(self, reason=None, on_write=False, post='UNCHANGED', real_signal=False):
        abort = s.CampaignAbort()
        abort.reason = reason
        groups = {g: dict(status='PASS', returncode=0) for g in range(48)}
        writes = []
        original_publish = s.atomic_publish
        def save(path, result):
            original_publish(path, result)
            writes.append(dict(result))
            if on_write and len(writes) == 1: abort.stop(dict(signal=15))
            if real_signal and len(writes) == 1: os.kill(os.getpid(), signal.SIGTERM)
        previous = signal.getsignal(signal.SIGTERM)
        try:
            signal.signal(signal.SIGTERM, lambda n, f: abort.stop(dict(signal=n)))
            with tempfile.TemporaryDirectory(prefix='host_terminal_', dir=s.base.HERE) as temporary:
                out = Path(temporary)
                with patch.object(s, 'atomic_publish', side_effect=save):
                    code = s.publish_campaign(out, dict(scope='host-only'), groups, abort, post)
                self.assertEqual(s.base.read(out / 'complete.json'), json.loads(json.dumps(writes[-1])))
                self.assertFalse(list(out.glob('*.pending')))
                self.assertTrue(abort.terminal)
        finally:
            signal.signal(signal.SIGTERM, previous)
        return code, writes

    def test_last_group_late_timeout_all_pass_cannot_pass_aggregate(self):
        code, writes = self.aggregate(dict(group=47, timeout=True))
        self.assertEqual(code, 1)
        self.assertEqual(writes[-1]['status'], 'CANDIDATE04_NF8_FULL192_NOT_PASS')

    def test_late_signal_after_all_rc_zero(self):
        code, writes = self.aggregate(dict(signal=15))
        self.assertEqual(code, 1)
        self.assertEqual(writes[-1]['firstfailure'], dict(signal=15))

    def test_signal_reentering_aggregate_write_revokes_pass(self):
        code, writes = self.aggregate(on_write=True)
        self.assertEqual(code, 1)
        self.assertEqual(len(writes), 2)
        self.assertEqual(writes[-1]['status'], 'CANDIDATE04_NF8_FULL192_NOT_PASS')

    def test_actual_sigterm_during_atomic_publication(self):
        code, writes = self.aggregate(real_signal=True)
        self.assertEqual(code, 1)
        self.assertEqual(writes[-1]['status'], 'CANDIDATE04_NF8_FULL192_NOT_PASS')
        self.assertEqual(writes[-1]['firstfailure'], dict(signal=15))

    def test_clean_aggregate_control_and_pin_drift(self):
        code, writes = self.aggregate()
        self.assertEqual(code, 0)
        self.assertEqual(writes[-1]['status'], 'CANDIDATE04_NF8_FULL192_PASS')
        self.assertEqual(self.aggregate(post='image changed')[0], 1)

    def test_actual_existing_preflight_plan_template_replaced(self):
        with tempfile.TemporaryDirectory(prefix='host_preflight_', dir=s.base.HERE) as temporary:
            out = Path(temporary)
            s.base.save(out / 'plan.json', dict(orchestration='old'))
            s.base.save(out / 'review.template.json', dict(parent_authorized=False, plan_sha256='old'))
            plan = dict(orchestration=s.VERSION, pins={})
            review = s.publish_preflight(out, plan)
            self.assertEqual(s.base.read(out / 'plan.json'), plan)
            self.assertEqual(s.base.read(out / 'review.template.json'), review)
            self.assertEqual(review['plan_sha256'], s.base.sha(out / 'plan.json'))
            self.assertFalse(review['parent_authorized'])
            self.assertFalse(list(out.glob('*.pending')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
