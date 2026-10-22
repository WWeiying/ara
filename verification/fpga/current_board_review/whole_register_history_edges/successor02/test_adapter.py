"""Focused lifecycle/file-publication negatives, not a new general framework suite."""
import json
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest.mock import patch
import driver as d


class Tests(unittest.TestCase):
    def test_deadline_during_finish_cannot_accept(self):
        with tempfile.TemporaryDirectory() as root:
            abort = d.Abort()
            now = [0]
            terminal = d.Terminal(abort, 10, now=lambda: now[0])
            terminal.guard()
            now[0] = 11
            with self.assertRaises(ValueError):
                terminal.accept(Path(root)/'complete.json', dict(status='PASS', returncode=0))
            self.assertIsNotNone(abort.reason)
            self.assertFalse((Path(root)/'complete.json').exists())

    def test_actual_timer_thread_while_finish_blocked(self):
        abort = d.Abort()
        terminal = d.Terminal(abort, 999999999999)
        t = threading.Timer(0.01, terminal.timeout)
        t.start()
        t.join(1)
        self.assertFalse(t.is_alive())
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                terminal.accept(Path(root)/'complete.json', dict(status='PASS', returncode=0))

    def test_filesystem_cancel_during_publication_rewrites_fail(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/'complete.json'
            abort = d.Abort()
            terminal = d.Terminal(abort, 100, now=lambda: 0)
            original = d.publish
            def interrupted(p, value):
                original(p, value)
                abort.stop(dict(signal=15))
            with patch.object(d, 'publish', side_effect=interrupted):
                with self.assertRaises(ValueError):
                    terminal.accept(path, dict(status='PASS'))
            d.publish(path, dict(status='NOT_ACCEPTED'))
            self.assertEqual(d.read(path)['status'], 'NOT_ACCEPTED')
            self.assertEqual([p.name for p in Path(root).iterdir()], ['complete.json'])

    def test_stale_timer_after_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            abort = d.Abort()
            terminal = d.Terminal(abort, 10, now=lambda: 0)
            terminal.accept(Path(root)/'complete.json', dict(status='PASS'))
            terminal.timeout()
            self.assertIsNone(abort.reason)

    def campaign(self, reason=None, now=0, pending=False, missing=False):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root)
            d.save(out/'plan.json', {})
            abort = d.Abort()
            if reason:
                abort.stop(reason)
            results = {g:dict(status='PASS', returncode=0, elapsed_s=1) for g in range(58 if missing else 59)}
            with patch.object(signal, 'sigpending', return_value={signal.SIGTERM} if pending else set()):
                rc = d.publish_campaign(out, results, abort, dict(image_sha256='image', scope='test'), 10, 'UNCHANGED', now=lambda: now)
            return rc, d.read(out/'complete.json')

    def test_last_group_late_rejects_aggregate(self):
        rc, end = self.campaign(now=11)
        self.assertEqual((rc, end['status']), (1, 'NOT_ACCEPTED'))

    def test_signal_cancel_rc0_rejects_aggregate(self):
        for kwargs in (dict(reason=dict(signal=15)), dict(pending=True), dict(missing=True)):
            rc, end = self.campaign(**kwargs)
            self.assertEqual((rc, end['status']), (1, 'NOT_ACCEPTED'))

    def test_clean_complete_filesystem(self):
        rc, end = self.campaign()
        self.assertEqual((rc, end['status']), (0, 'M4_MISSING59_BOUNDARY_SUPPLEMENT_PASS'))

    def test_console_contradiction(self):
        case = d.read(d.PREDECESSOR)['cases'][0]
        good = '\n'.join(case['pass_markers'])+'\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
        d.console_ok(good, case)
        for extra in ('RVV_WHOLE_FAIL', 'TIMEOUT', 'BOARD_REPLAY_TRAP', 'CANCELLED'):
            with self.assertRaises(ValueError):
                d.console_ok(good+extra, case)
        with self.assertRaises(ValueError):
            d.console_ok(good.replace('skips=1', 'skips=2'), case)

    def test_worker_refuses_without_authorization(self):
        with self.assertRaises(ValueError):
            d.worker(Path('/nonexistent'), None, False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
