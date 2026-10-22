"""Actual filesystem/timer/SIGTERM terminal tests, not a DUT or reference run."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import checker as c
import replay as r
import terminal_publish as t


class Terminal(unittest.TestCase):
    def test_abort_timer_while_pending_json_written(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);abort=t.TerminalAbort();terminal={'status':r.PASS}
            original=t.write_json
            def slow(path,data,mode='x'):
                original(path,data,mode)
                if mode=='x':
                    fired=threading.Event()
                    def callback():abort.set();fired.set()
                    timer=threading.Timer(0.01,callback);timer.start()
                    self.assertTrue(fired.wait(2));timer.join()
            with patch.object(t,'write_json',side_effect=slow):t.publish(out,terminal,abort,time.monotonic()+10)
            actual=c.read(out/'complete.json')
            self.assertEqual(actual['status'],'NOT_ACCEPTED_LATE_ABORT')
            self.assertTrue(actual['aborted']);self.assertFalse((out/'complete.pending.json').exists())

    def test_real_sigterm_during_pending_filesystem_write(self):
        with tempfile.TemporaryDirectory() as d:
            script="""import os,signal,time
from pathlib import Path
import checker as c, replay as r, terminal_publish as t
out=Path(__import__('sys').argv[1]);abort=t.TerminalAbort();terminal={'status':r.PASS}
original=t.write_json
def signalled(path,data,mode='x'):
    original(path,data,mode)
    if mode=='x':os.kill(os.getpid(),signal.SIGTERM)
t.write_json=signalled
with c.common.abort_signals(abort):t.publish(out,terminal,abort,time.monotonic()+10)
raise SystemExit(int(terminal['status']!=r.PASS))
"""
            q=subprocess.run([sys.executable,'-B','-c',script,d],cwd=c.HERE,
                text=True,capture_output=True,timeout=10)
            self.assertEqual(q.returncode,1,(q.stdout,q.stderr))
            actual=c.read(Path(d)/'complete.json')
            self.assertEqual(actual['status'],'NOT_ACCEPTED_LATE_ABORT');self.assertTrue(actual['aborted'])

    def test_expired_without_callback_and_pending_signal(self):
        for expired in (True,False):
            with self.subTest(expired=expired),tempfile.TemporaryDirectory() as d:
                out=Path(d);abort=t.TerminalAbort();terminal={'status':r.PASS}
                with patch.object(t.signal,'sigpending',return_value=set() if expired else {signal.SIGTERM}):
                    t.publish(out,terminal,abort,time.monotonic()+(-1 if expired else 10))
                self.assertEqual(c.read(out/'complete.json')['status'],'NOT_ACCEPTED_LATE_ABORT')

    def test_absolute_deadline_expires_during_write(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);abort=t.TerminalAbort();terminal={'status':r.PASS}
            original=t.write_json
            def slow(path,data,mode='x'):
                original(path,data,mode)
                if mode=='x':time.sleep(0.04)
            with patch.object(t,'write_json',side_effect=slow):
                t.publish(out,terminal,abort,time.monotonic()+0.02)
            self.assertEqual(c.read(out/'complete.json')['status'],'NOT_ACCEPTED_LATE_ABORT')

    def test_success_closes_late_callback_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);abort=t.TerminalAbort();terminal={'status':r.PASS}
            t.publish(out,terminal,abort,time.monotonic()+10)
            self.assertEqual(c.read(out/'complete.json')['status'],r.PASS)
            self.assertTrue(abort.closed);abort.set();self.assertFalse(abort.is_set())
            before=(out/'complete.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'No terminal overwrite'):
                t.publish(out,terminal,abort,time.monotonic()+10)
            self.assertEqual((out/'complete.json').read_bytes(),before)

    def test_write_failure_never_publishes_pass(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            with patch.object(t.os,'fsync',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):t.publish(out,{'status':r.PASS},t.TerminalAbort(),time.monotonic()+10)
            self.assertFalse((out/'complete.json').exists())

    def test_preserved_checker_host_and_exact_narrow_delta(self):
        proof=c.read(c.HERE/'successor_proof.json');c.common.base.verify_pins(proof['old_input_pins'])
        self.assertEqual(c.sha(c.HERE/'checker.py'),proof['old_checker_sha256'])
        old=c.read(c.HERE.parent/'vcs_m8_plan01/host02.json')
        self.assertEqual((old['tests'],old['actual_child_returncode'],old['errors'],old['failures']),(21,0,0,0))
        source=(c.HERE/'replay.py').read_text()
        self.assertIn('deadline.cancel();deadline.join()',source)
        self.assertIn('abort,done=terminal_publish.TerminalAbort(),threading.Event()',source)
        self.assertIn('terminal_publish.publish(out,terminal,abort,expires)',source)
        self.assertNotIn("save(out/'complete.json',terminal)",source)


if __name__=='__main__':unittest.main()
