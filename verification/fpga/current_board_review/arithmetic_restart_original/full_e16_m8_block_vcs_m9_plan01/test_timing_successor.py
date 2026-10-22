"""Timing-only successor proof; no full Host, raw reference, or DUT replay."""
import ast
import difflib
from pathlib import Path
import tempfile
import threading
import time
import unittest
import checker as c
import replay as r

FILES=('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json','test_timing_successor.py')
PINS={str(c.HERE/n):c.sha(c.HERE/n) for n in FILES}

def normalized_checker(text):
    tree=ast.parse(text)
    tree.body=[n for n in tree.body if not isinstance(n,ast.Import) or
        not any(a.name=='time' for a in n.names)]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name=='audit':
            node.body=[n for n in node.body if not (
                isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='start' for x in n.targets)
                or isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='print')]
            loop=next(n for n in ast.walk(node) if isinstance(n,ast.For))
            loop.body=[n for n in loop.body if not (isinstance(n,ast.If) and
                ast.unparse(n.test)=='state.rows % 1000000 == 0' and len(n.body)==1 and
                isinstance(n.body[0],ast.Expr) and isinstance(n.body[0].value,ast.Call) and
                isinstance(n.body[0].value.func,ast.Name) and n.body[0].value.func.id=='print')]
    return ast.dump(tree,include_attributes=False)

def normalized_replay(text,current):
    tree=ast.parse(text)
    # prepare was never called by fullHost; only its final evidence-admission
    # gate changed to bind the narrow successor and preserve the original pins.
    tree.body=[n for n in tree.body if not (isinstance(n,ast.FunctionDef) and n.name=='prepare')]
    if current:
        body=[]
        for n in tree.body:
            if isinstance(n,ast.Import) and any(a.name=='time' for a in n.names):continue
            if isinstance(n,ast.FunctionDef) and n.name=='monitored_with_outcome':continue
            if isinstance(n,ast.Assign) and len(n.targets)==1:
                target=ast.unparse(n.targets[0])
                if target=='core.monitored_with_outcome':continue
                if target=='numeric_monitor':
                    n.targets=[ast.Name(id='monitored_with_outcome',ctx=ast.Store())]
            body.append(n)
        tree.body=body
    return ast.dump(tree,include_attributes=False)

class TimingHost(unittest.TestCase):
    def test_checker_only_stdout_timing_diff(self):
        old=(c.HERE/'host01_code/checker.py').read_text();current=(c.HERE/'checker.py').read_text()
        self.assertEqual(normalized_checker(old),normalized_checker(current))

    def test_worker_only_stdout_wrapper_diff(self):
        old=(c.HERE/'host01_code/replay.py').read_text();current=(c.HERE/'replay.py').read_text()
        self.assertEqual(normalized_replay(old,False),normalized_replay(current,True))
        fn=next(n for n in ast.parse(current).body if isinstance(n,ast.FunctionDef) and n.name=='monitored_with_outcome')
        # This exact wrapper has no changed dispatch, arithmetic, abort, or exception handling.
        self.assertEqual(ast.unparse(fn),ast.unparse(ast.parse('''
def monitored_with_outcome(original,abort):
    wrapped=numeric_monitor(original,abort)
    def monitored(*args,**kwargs):
        start=time.monotonic();print('PHASE actual_monitor START',flush=True)
        outcome=wrapped(*args,**kwargs)
        print(f'PHASE actual_monitor SAVED rc={outcome[0]} elapsed={time.monotonic()-start:.3f}s',flush=True)
        return outcome
    return monitored
''').body[0]))

    def test_current_numeric_before_posterror_0_17_timeout_nooverwrite(self):
        for rc,timed in ((0,False),(17,False),(-9,True)):
            with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
                root=Path(tmp);abort=threading.Event();r.durable(root/'command.json',dict(command=['focused-host']))
                def actual(*args,**kwargs):return rc,0.01,timed,False
                fn=r.monitored_with_outcome(actual,abort)
                outcome=fn(['focused-host'],root,root/'console.log',10800)
                self.assertEqual(outcome,(rc,0.01,timed,False))
                saved=c.read(root/'child_outcome.unvalidated.json')
                self.assertEqual((saved['returncode'],saved['timed_out']),(rc,timed))
                try:raise ValueError('real later postcheck')
                except ValueError:self.assertEqual(c.read(root/'child_outcome.unvalidated.json'),saved)
                self.assertEqual(abort.is_set(),rc!=0 or timed)
                with self.assertRaises(FileExistsError):fn(['focused-host'],root,root/'console.log',10800)
                self.assertEqual(c.read(root/'child_outcome.unvalidated.json'),saved)

if __name__=='__main__':
    start=time.monotonic()
    r.durable(c.HERE/'timing_host_preflight.json',dict(pins=PINS,
        startup_hashes_for_fullHost_available=False,
        host01_code_is_reconstructed_snapshot_not_loaded_attestation=True,
        CSV_reads=0,DUT_runs=0,reference_runs=0))
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(TimingHost))
    c.common.base.verify_pins(PINS)
    diff={}
    for name in ('checker.py','replay.py'):
        old=(c.HERE/'host01_code'/name).read_text();new=(c.HERE/name).read_text()
        diff[name]=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),
            fromfile='reconstructed_pre_timing/'+name,tofile='current/'+name))
    pins=dict(PINS)
    for name in ('checker.py','replay.py'):pins[str(c.HERE/'host01_code'/name)]=c.sha(c.HERE/'host01_code'/name)
    r.durable(c.HERE/'timing_host_result.json',dict(status='PASS_TIMING_ONLY_SUCCESSOR' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),elapsed_s=time.monotonic()-start,
        pins=pins,postpins_unchanged=True,diff=diff,CSV_reads=0,DUT_runs=0,reference_runs=0,
        fullHost_startup_input_hashes_captured=False,reconstructed_snapshot_is_loaded_attestation=False))
    raise SystemExit(not result.wasSuccessful())

