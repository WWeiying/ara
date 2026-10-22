"""Narrow correction of a negative's message expectation, not checker semantics."""
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest
import checker as c
from host_records import Builder
from test_host import deepcopy
HERE=c.HERE

class Negatives(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        state=c.Strict(c.specification());builder=Builder(state.spec)
        for row in builder.records():
            state.consume(row)
            if state.init_index==101 and not state.calls:
                cls.partial=deepcopy(state);break
        assert len(state.fresh['out'])==802 and state.init_index==101
        cls.spec=state.spec
    def reach_helper(self,old_values):
        state=deepcopy(self.partial);builder=Builder(self.spec)
        if old_values:
            for i in range(1026):state.memory[state.s['out']+i]=91
        builder.order=state.retired;builder.regs=state.regs.copy()
        for reg,value in enumerate([state.s['a'],state.s['b'],state.s['out']+1,0,1024,state.s['mask'],0],10):
            state.consume(builder.setreg(reg,value))
        return state,builder.row(state.helpers['op_0'][0]['pc'],5,1024)
    def test_first_call_middle_sh_missing28_values(self):
        state,row=self.reach_helper(False)
        with self.assertRaisesRegex(ValueError,'^Actual source initialized values out$'):state.consume(row)
    def test_old_same_values_missing28_fresh_writes(self):
        state,row=self.reach_helper(True)
        with self.assertRaisesRegex(ValueError,'^Deleted fresh source initialization out$'):state.consume(row)

if __name__=='__main__':
    names=('checker.py','host_records.py','test_host.py','host_negative03.py','reset_profile.json','replay.py')
    pins={str(HERE/n):c.sha(HERE/n) for n in names}
    from replay import durable
    if sys.argv[1:]==['--child']:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Negatives))
        durable(HERE/'host_negative03.json',dict(status='PASS_FOCUSED_HOST_NEGATIVES_NOT_DUT' if result.wasSuccessful() else 'FAIL',
            tests=result.testsRun,failures=len(result.errors)+len(result.failures),pins=pins,full_stream_repeated=False,
            DUT_runs=0,reference_runs=0))
        raise SystemExit(not result.wasSuccessful())
    assert not sys.argv[1:]
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--child']
    durable(HERE/'host_negative03_command.json',dict(command=command,timeout_s=60,pins=pins))
    began=time.monotonic();timed=False
    with (HERE/'host_negative03.log').open('x') as log:
        child=subprocess.Popen(command,cwd=HERE,stdout=log,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=60)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
    unchanged=all(c.sha(Path(path))==digest for path,digest in pins.items())
    durable(HERE/'host_negative03_exit.json',dict(returncode=rc,timed_out=timed,pid=child.pid,
        elapsed_s=time.monotonic()-began,pins_unchanged=unchanged))
    print(dict(returncode=rc,timed_out=timed,pins_unchanged=unchanged),flush=True)
    raise SystemExit(rc if not timed and unchanged else 124)
