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

    def test_real_signal_inside_fsync_and_before_rename(self):
        for phase in ('fsync','rename'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as d:
                script="""import os,signal,time
from pathlib import Path
import checker as c, replay as r, terminal_publish as t
out=Path(__import__('sys').argv[1]);phase=__import__('sys').argv[2]
abort=t.TerminalAbort();terminal={'status':r.PASS};fired=[False]
old_sync=t.os.fsync;old_rename=t.os.replace
def injected_sync(fd):
    old_sync(fd)
    if phase=='fsync' and not fired[0]:
        fired[0]=True;os.kill(os.getpid(),signal.SIGTERM)
def injected_rename(a,b):
    if phase=='rename' and not fired[0]:
        fired[0]=True;os.kill(os.getpid(),signal.SIGTERM)
    old_rename(a,b)
t.os.fsync=injected_sync;t.os.replace=injected_rename
with c.common.abort_signals(abort):t.publish(out,terminal,abort,time.monotonic()+10)
assert fired[0] and terminal['status']==c.read(out/'complete.json')['status']
raise SystemExit(int(terminal['status']!=r.PASS))
"""
                q=subprocess.run([sys.executable,'-B','-c',script,d,phase],cwd=c.HERE,
                    text=True,capture_output=True,timeout=10)
                self.assertEqual(q.returncode,1,(q.stdout,q.stderr))
                self.assertEqual(c.read(Path(d)/'complete.json')['status'],'NOT_ACCEPTED_LATE_ABORT')

    def test_cancel_join_of_already_started_timer_callback(self):
        with tempfile.TemporaryDirectory() as d:
            started=threading.Event();release=threading.Event();abort=t.TerminalAbort()
            def callback():
                started.set();release.wait(2);abort.set()
            timer=threading.Timer(0.001,callback);timer.start()
            self.assertTrue(started.wait(2));timer.cancel()
            releaser=threading.Timer(0.01,release.set);releaser.start()
            timer.join();releaser.join()
            self.assertFalse(timer.is_alive());self.assertTrue(abort.is_set())
            out=Path(d);terminal={'status':r.PASS}
            t.publish(out,terminal,abort,time.monotonic()+10)
            self.assertEqual(c.read(out/'complete.json')['status'],'NOT_ACCEPTED_LATE_ABORT')

    def test_no_new_postcommit_directory_fsync(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);calls=[];original=t.os.fsync
            def fsync(fd):
                import stat
                self.assertFalse(stat.S_ISDIR(os.fstat(fd).st_mode))
                calls.append(fd);original(fd)
            with patch.object(t.os,'fsync',side_effect=fsync):
                t.publish(out,{'status':r.PASS},t.TerminalAbort(),time.monotonic()+10)
            self.assertEqual(len(calls),1)
            self.assertEqual(c.read(out/'complete.json')['status'],r.PASS)


if __name__=='__main__':unittest.main()
