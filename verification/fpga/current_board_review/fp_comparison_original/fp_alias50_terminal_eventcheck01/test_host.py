"""Focused terminal automation tests; no DUT/reference/raw consumption."""
import copy
import csv
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import audit as a

class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.worker,cls.protocol,cls.Observer=a.modules()
        cls.spec=a.read(a.RUN/'plan.json')['specs'][a.NAME]
        cls.insn=cls.spec['routines'][0][7]['insn']
        cls.pc=cls.spec['routines'][0][7]['pc']

    def rows(self):
        base=dict(cycle='0',event='',order='0',port='0',trans_id='0',pc=f'{self.pc:x}',
            insn=self.insn,rd='0',rd_wdata='0',mem_addr='0',mem_rmask='0',mem_wmask='0',mem_wdata='0',trap='0')
        result=[]
        for k,e in enumerate(('cvx_req','arch_start','uop_alloc','uop_done','cvx_resp','retire')):
            result.append(dict(base,event=e,cycle=str(k)))
        return result

    def stream(self,rows):
        s=io.StringIO()
        w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        s.seek(0);return s

    def observed(self,rows):
        observer=self.Observer(self.protocol)
        list(observer.rows(csv.DictReader(self.stream(rows))))
        return observer.finish()

    def test_six_protocol_events_equal_actual_frozen_generic(self):
        rows=self.rows()
        with tempfile.TemporaryDirectory(dir=a.HERE) as tmp:
            p=Path(tmp)/'host.csv';p.write_text(self.stream(rows).getvalue())
            self.assertEqual(self.observed(rows),self.protocol.validate_trace(p))

    def test_unknown_partial_trap_and_corrupt_uop_rejected(self):
        rows=self.rows()
        for bad in [rows[:-1],rows[:4]+rows[5:]]:
            with self.assertRaises((ValueError,AssertionError,KeyError)):self.observed(bad)
        for index,field,value in [(2,'event','unknown'),(4,'trap','1'),(3,'order','1')]:
            bad=copy.deepcopy(rows);bad[index][field]=value
            with self.assertRaises((ValueError,AssertionError,KeyError)):self.observed(bad)

    def test_numeric_saved_before_any_postcheck0_17_timeout(self):
        class Process:
            pid=123
            def __init__(self,code,timeout=False):self.code=code;self.timeout=timeout;self.killed=False
            def wait(self,timeout=None):
                if self.timeout and not self.killed:raise subprocess.TimeoutExpired('Host only',1)
                return self.code
            def kill(self):self.killed=True
        for code,timeout in [(0,False),(17,False),(-9,True)]:
            with tempfile.TemporaryDirectory(dir=a.HERE) as tmp,patch.object(a,'OUT',Path(tmp)):
                proc=Process(code,timeout)
                self.assertEqual(a.wait_child(proc,time.monotonic(),1),(code,timeout))
                with self.assertRaises(ValueError):raise ValueError('Host postcheck error')
                receipt=a.read(Path(tmp)/'actual_exit_unvalidated.json')
                self.assertEqual(receipt['returncode'],code)
                self.assertEqual(receipt['timed_out'],timeout)
                self.assertFalse(receipt['validated'])

    def test_worker_identity_rejects_wrong_pid_lifetime_command_group(self):
        ready=dict(worker_command=['actual','run'],worker_cgroup='/actual/unit',worker_start_ticks=123)
        a.identity(['actual','run'],'0::/actual/unit\n',123,ready)
        for argv,group,ticks in [(['wrong'],'0::/actual/unit',123),
                                 (['actual','run'],'0::/wrong',123),
                                 (['actual','run'],'0::/actual/unit',124)]:
            with self.assertRaises(ValueError):a.identity(argv,group,ticks,ready)

    def test_unchanged_source_scope_and_marker_policy_pinned(self):
        plan=a.read(a.RUN/'plan.json')
        self.assertEqual((plan['jobs'],plan['timeout_s'],plan['service_timeout_s']),(1,7200,9000))
        self.assertEqual(a.sha(a.RUN/'plan.json'),a.PLAN_SHA)
        self.assertEqual(a.sha(a.WORK/'parent_review.json'),a.PARENT_SHA)
        self.assertEqual(self.spec['routines'][0][7]['insn'],'62881457')
        self.worker.checker.console_gate('\n'.join(plan['cases'][0]['pass_markers']+
            [self.worker.common.SUCCESS,'$finish'])+'\n')
        self.assertEqual(a.read(self.worker.OLD/'host02.json')['source_data_positives'],2)
        self.assertEqual(a.read(self.worker.OLD/'host02.json')['source_mutations'],19)

if __name__=='__main__':
    start=time.monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Gates))
    paths=[a.HERE/f for f in ('audit.py','observer.py','test_host.py','README.md')]
    a.save(a.HERE/'host01.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        elapsed_s=time.monotonic()-start,pins={str(p):a.sha(p) for p in paths},
        numeric_postcheck_codes=[0,17],timeout_negative=-9,raw_CSV_reads=0,DUT_REF_started=False))
    raise SystemExit(not result.wasSuccessful())
