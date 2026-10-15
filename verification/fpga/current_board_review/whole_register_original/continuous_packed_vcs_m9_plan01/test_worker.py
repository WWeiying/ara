"""Local lifecycle Host only; real SIGTERM children, never a simulator."""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import replay as r
import checker as c

CHILD='''
import os,sys,time
from pathlib import Path
import replay as r
root=Path(sys.argv[1]);mode=sys.argv[2];abort=r.TerminalAbort();terminal=dict(status=r.PASS)
with r.common.abort_signals(abort):
    if mode=='before':os.kill(os.getpid(),15)
    original=r.os.replace
    if mode=='rename':
        def inject(*args):
            result=original(*args);os.kill(os.getpid(),15);return result
        r.os.replace=inject
    r.publish(root,terminal,abort,time.monotonic()+(-1 if mode=='deadline' else 30))
    if mode=='after_seal':os.kill(os.getpid(),15)
    r.durable(root/'observed.json',dict(terminal=terminal,abort=abort.is_set(),closed=abort.closed))
raise SystemExit(0 if terminal['status']==r.PASS else 1)
'''
class Worker(unittest.TestCase):
    def test_real_signal_and_deadline_children(self):
        receipts=[]
        for mode in ('normal','before','rename','deadline','after_seal'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                began=time.monotonic();p=subprocess.Popen([sys.executable,'-B','-c',CHILD,d,mode],cwd=r.HERE,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                out,err=p.communicate(timeout=15)
                expected=0 if mode in ('normal','after_seal') else 1
                self.assertEqual(p.returncode,expected,(out,err))
                record=r.read(Path(d)/'complete.json');observed=r.read(Path(d)/'observed.json')
                self.assertEqual(record,observed['terminal']);self.assertEqual(record['aborted'],bool(expected))
                self.assertTrue(observed['closed'])
                receipts.append(dict(mode=mode,pid=p.pid,returncode=p.returncode,elapsed_s=time.monotonic()-began,terminal=record))
        self.__class__.receipts=receipts
    def test_numeric_wait_saved_before_postchecks(self):
        for outcome in ((0,0.1,False,False),(124,0.2,True,False),(-15,0.3,False,False),(0,0.4,False,True)):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);r.durable(root/'command.json',dict(command=['host_no_simulator']))
                abort=r.TerminalAbort()
                def original(*args):return outcome
                returned=r.monitored_with_outcome(original,abort)(['host_no_simulator'],root,root/'console.log',1)
                saved=r.read(root/'child_outcome.unvalidated.json')
                self.assertEqual(returned,outcome);self.assertEqual(saved['returncode'],outcome[0])
                self.assertEqual(abort.is_set(),bool(outcome[0] or outcome[2] or outcome[3]))
                self.assertFalse(saved['architectural_acceptance'])
    def test_late_plan_drift(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r.durable(root/'plan.json',dict(value=1));digest=r.sha(root/'plan.json')
            (root/'plan.json').unlink();r.durable(root/'plan.json',dict(value=2))
            with self.assertRaisesRegex(ValueError,'Late disk plan drift'):r.terminal_disk_gate(root,digest,r.IMAGE)
    def test_stream_rejects_numeric_bad_before_csv(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);r.durable(root/'child_outcome.unvalidated.json',dict(returncode=1,timed_out=False,failure_seen=False,cancelled=False))
            with self.assertRaisesRegex(ValueError,'Numeric wait before CSV'):
                c.stream_validate(root/'DOES_NOT_EXIST.csv',threading.Event())
    def test_exact_ownership_fields(self):
        props=dict(Id=r.UNIT,LoadState='loaded',ActiveState='active',SubState='running',MainPID='123',
            ControlGroup='/test/'+r.UNIT,RuntimeMaxUSec='3h 40min',KillMode='control-group',Restart='no')
        r.owner_gate(props,'0::/test/'+r.UNIT,123)
        for key,value in [('MainPID','124'),('RuntimeMaxUSec','4h'),('KillMode','process'),('Restart','always')]:
            with self.subTest(key=key),self.assertRaises(ValueError):r.owner_gate(dict(props,**{key:value}),'0::/test/'+r.UNIT,123)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Worker))
    c.save(c.HERE/'host_worker02.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'NOT_PASS',tests=result.testsRun,
        failures=len(result.failures)+len(result.errors),signal_children=getattr(Worker,'receipts',None),
        pins={str(c.HERE/n):c.sha(c.HERE/n) for n in ('replay.py','test_worker.py','checker.py')}))
    raise SystemExit(int(not result.wasSuccessful()))
