"""Focused synthetic metadata/transport checks only; no real CSV or DUT queries."""
import copy
from collections import Counter
import hashlib
import io
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode=True
import audit as a


class Gates(unittest.TestCase):
    def setUp(self):
        self.plan=dict(cases=[dict(id=n) for n in a.NAMES])
        self.summary=[dict(name=n,kind='app',status='PASS',reason='',returncode=0,elapsed_s=1.0) for n in a.NAMES]
        self.done=dict(status=a.PASS,plan_sha256=a.PLAN_SHA,image_sha256=a.IMAGE_SHA,aborted=False,retries=0,
            pins_unchanged=True,results=self.summary,trials=list(range(96)),groups=24,checks=284816,checkpoints=168,Linux_replay=False)
        self.run=dict(status='COMPLETE',tests=a.NAMES,status_counts={'PASS':24},jobs=4,timeout_s=2400,seed=1,
            commit_trace=True,input_snapshots=True,code_coverage=False,contract_monitor=False,probe_kinds=[],
            created_at='2026-10-12T00:00:00+00:00',completed_at='2026-10-12T00:01:00+00:00')
        self.command=dict(command=['synthetic_not_executed'],cwd='/synthetic/work')
        self.child=dict(schema='UNVALIDATED_SIMULATOR_OUTCOME_V1',returncode=0,elapsed_s=1.0,timed_out=False,
            failure_seen=False,architectural_acceptance=False,command=self.command['command'],cwd=self.command['cwd'],command_sha256='fixed')
    def check(self):a.complete_fields(self.plan,self.done,self.run,self.summary)
    def reject(self):
        with self.assertRaises((AssertionError,KeyError,TypeError)):self.check()
    def test_complete_positive(self):self.check()
    def test_missing_member(self):self.summary.pop();self.reject()
    def test_reordered_members(self):self.summary.reverse();self.reject()
    def test_boolean_exit(self):self.summary[0]['returncode']=False;self.reject()
    def test_numeric_failure(self):self.summary[0]['returncode']=17;self.reject()
    def test_nonpass_status(self):self.summary[0]['status']='ERROR';self.reject()
    def test_abort(self):self.done['aborted']=True;self.reject()
    def test_retry(self):self.done['retries']=1;self.reject()
    def test_boolean_retry(self):self.done['retries']=False;self.reject()
    def test_pin_failure(self):self.done['pins_unchanged']=False;self.reject()
    def test_partial_runner(self):self.run['status']='RUNNING';self.reject()
    def test_wrong_image(self):self.done['image_sha256']='wrong';self.reject()
    def test_wrong_plan(self):self.done['plan_sha256']='wrong';self.reject()
    def test_missing_oracle_scope(self):self.done['checks']=284815;self.reject()
    def test_elapsed_nan(self):self.summary[0]['elapsed_s']=float('nan');self.reject()
    def test_elapsed_over_bound(self):self.summary[0]['elapsed_s']=2400.1;self.reject()
    def test_child_positive(self):a.child_fields(self.summary[0],self.child,self.command,'fixed')
    def test_child_negatives(self):
        for key,value in [('returncode',False),('returncode',17),('timed_out',True),('failure_seen',True),
                          ('architectural_acceptance',True),('command_identity_error','missing command'),
                          ('command_sha256','wrong'),('command',['wrong'])]:
            with self.subTest(key=key,value=value):
                child=dict(self.child);child[key]=value
                with self.assertRaises(AssertionError):a.child_fields(self.summary[0],child,self.command,'fixed')
    def test_lossless_transport_and_mutation(self):
        transport=a.load(a.u.TRANSPORT,'nf7_host_lossless_rows')
        class Observer(transport.Observer):
            def __init__(self):self.count=Counter();self.before=hashlib.sha256();self.after=hashlib.sha256()
            def observe(self,row):pass
        class Reader:
            fieldnames=transport.FIELDS
            def __iter__(self):return iter([{k:'0' for k in self.fieldnames}])
        observer=Observer();list(observer.rows(Reader()))
        self.assertEqual(observer.before.digest(),observer.after.digest())
        self.assertEqual(observer.count['unmodified_delivered_rows'],1)
        iterator=Observer().rows(Reader());row=next(iterator);row['pc']='altered'
        with self.assertRaises(AssertionError):next(iterator)


def main():
    out=a.HERE/'host01';out.mkdir();stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Gates))
    with (out/'log.txt').open('x') as log:log.write(stream.getvalue())
    pins={str(a.HERE/n):a.sha(a.HERE/n) for n in ('audit.py','wait_terminal.py','test_host.py','README.md')}
    pins.update({str(a.OLD/'audit.py'):a.OLD_SHA,str(a.OLD/'wait_terminal.py'):a.WAIT_SHA,str(a.u.TRANSPORT):a.u.TRANSPORT_SHA})
    a.verify(pins)
    a.save(out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'HOST_NOT_PASS',
        tests=result.testsRun,failures=len(result.failures)+len(result.errors),exit_code=0 if result.wasSuccessful() else 1,
        pins=pins,log_sha256=a.sha(out/'log.txt'),synthetic_only=True,actual_CSV_reads=0,DUT_launches=0))
    print(stream.getvalue(),end='');return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
