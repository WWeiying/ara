"""Only new event/meta/single-stream adapter gates; no full source Host rerun."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import terminal as t


class Gates(unittest.TestCase):
    def fixtures(self):
        cases = [dict(id='arithmetic_full_e32_mf2')]
        results = [dict(name=c['id'],status='PASS',returncode=0,reason='',elapsed_s=1) for c in cases]
        complete = dict(status=t.WORKER_PASS,plan_sha256=t.PLAN_SHA,aborted=False,pins_unchanged=True,retries=0,results=results)
        meta = dict(status='COMPLETE',status_counts={'PASS':1},tests=['arithmetic_full_e32_mf2'],jobs=1,timeout_s=10800,
                    commit_trace=True,code_coverage=False,completed_at='actual')
        return complete,meta,results,cases

    def test_whole1_gate(self):
        c,m,r,s = self.fixtures()
        t.terminal_gate(c,m,r,s)
        for key,value in [('status','NOT_PASS'),('aborted',True),('pins_unchanged',False),('retries',1),
                          ('first_failure',{'error':'x'}),('error','postcheck'),('plan_sha256','wrong')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                t.terminal_gate(dict(c,**{key:value}),m,r,s)
        for key,value in [('status','RUNNING'),('jobs',2),('completed_at',None),('tests',['b','a'])]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                t.terminal_gate(c,dict(m,**{key:value}),r,s)
        for value in (None,True,1,-9):
            bad=deepcopy(r);bad[0]['returncode']=value
            with self.assertRaises(ValueError):
                t.terminal_gate(dict(c,results=bad),m,bad,s)

    def test_monitor_gate(self):
        command=dict(command=['simv','private'],cwd='/private')
        result=dict(elapsed_s=1.5)
        outcome=dict(schema='UNVALIDATED_CHILD_OUTCOME_V2',architectural_acceptance=False,returncode=0,
                     timed_out=False,failure_seen=False,cancelled=False,elapsed_s=1.5,**command)
        t.outcome_gate(outcome,result,command)
        for key,value in [('returncode',True),('returncode',-9),('timed_out',True),('failure_seen',True),
                          ('cancelled',True),('elapsed_s',1),('command',['simv','other']),('architectural_acceptance',True)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                t.outcome_gate(dict(outcome,**{key:value}),result,command)

    def test_process_identity(self):
        argv=['/usr/bin/python3','-B',str(t.WORK/'replay.py'),'run','--image',
              '/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image','--out',str(t.RUN),
              '--plan-sha256',t.PLAN_SHA,'--authorize-run','--entry-review',str(t.ENTRY),
              '--entry-review-sha256',t.ENTRY_SHA,'--parent-review',str(t.WORK/'parent_review.json'),
              '--parent-review-sha256',t.PARENT_SHA]
        t.process_identity(argv,'0::'+t.GROUP)
        with self.assertRaises(ValueError): t.process_identity(argv,'0::/wrong')
        with self.assertRaises(ValueError): t.process_identity(argv[:-1]+['wrong'],'0::'+t.GROUP)

    def test_pidfd_real_scalar_child(self):
        child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(0.2)'])
        fd=os.pidfd_open(child.pid)
        try:
            with self.assertRaisesRegex(ValueError,'timeout'): t.wait_fd(fd,0)
            t.wait_fd(fd,3)
            self.assertEqual(child.wait(timeout=1),0)
        finally:
            os.close(fd)
            if child.poll() is None: child.kill(); child.wait()

    def test_cgroup_gate(self):
        with tempfile.TemporaryDirectory(dir=t.HERE) as tmp:
            root=Path(tmp);path=root/t.GROUP.lstrip('/')
            self.assertEqual(t.empty_cgroup(root)['state'],'removed')
            path.mkdir(parents=True)
            (path/'cgroup.procs').write_text('')
            (path/'cgroup.events').write_text('populated 0\nfrozen 0\n')
            self.assertEqual(t.empty_cgroup(root)['state'],'empty')
            (path/'cgroup.procs').write_text('123\n')
            with self.assertRaises(ValueError): t.empty_cgroup(root)

    def test_single_pass_lossless_fanout(self):
        header='cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap\r\n'
        row='1,retire,0,0,-1,80000000,00000013,0,0,0,0,0,0,0\r\n'
        class Sink:
            def __init__(self): self.rows=[]
            def consume(self,row): self.rows.append(row)
            def finish(self): return dict(rows=len(self.rows))
        with tempfile.TemporaryDirectory(dir=t.HERE) as tmp:
            path=Path(tmp)/'fixture.csv';path.write_bytes((header+row).encode())
            sink=Sink();generic=t.load_module('host_private_generic',t.GENERIC)
            general,specific,digest,_=t.one_pass(path,sink,generic,lambda:None)
            self.assertEqual((general['retire_count'],specific['rows']),(1,1))
            self.assertEqual(digest,hashlib.sha256((header+row).encode()).hexdigest())
            for bad in (row.replace('retire','unknown'),row.replace(',0,0,0,0,0,0,0\r\n',',0\r\n')):
                path.write_bytes((header+bad).encode())
                with self.assertRaises(ValueError):
                    t.one_pass(path,Sink(),t.load_module('host_bad_generic',t.GENERIC),lambda:None)

    def test_sticky_abort_publication(self):
        with tempfile.TemporaryDirectory(dir=t.HERE) as tmp:
            t.ABORT=True
            try:
                with self.assertRaises(ValueError): t.publish_success(Path(tmp),dict(status='PASS'))
                self.assertFalse((Path(tmp)/'TERMINAL.json').exists())
            finally:
                t.ABORT=False

    def test_exclusive_output(self):
        with tempfile.TemporaryDirectory(dir=t.HERE) as tmp:
            path=Path(tmp)/'FIRST_ERROR.json'
            t.save(path,dict(error='first'))
            with self.assertRaises(FileExistsError): t.save(path,dict(error='second'))
            self.assertEqual(t.read(path),dict(error='first'))


if __name__ == '__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Gates))
    t.save(t.HERE/'host01.json',dict(status='PASS_NEW_GATES_ONLY' if result.wasSuccessful() else 'FAIL_NEW_GATES',
           tests=result.testsRun,failures=len(result.failures)+len(result.errors),full_source_Host_runs=0,
           raw_parses=0,pins={str(p):t.sha(p) for p in (t.HERE/'terminal.py',Path(__file__).resolve(),t.GENERIC)}))
    sys.exit(not result.wasSuccessful())
