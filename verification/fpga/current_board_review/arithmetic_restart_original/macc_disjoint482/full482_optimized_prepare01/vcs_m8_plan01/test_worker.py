"""No simulator: actual monitor-boundary persistence and fail-closed launch gates."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
import checker as c
import replay as r


class Worker(unittest.TestCase):
    def test_actual_numeric_outcomes_persist_before_generic_exception(self):
        for code,timeout,failure in ((0,False,False),(17,False,False),(0,True,False),(0,False,True)):
            with self.subTest(code=code,timeout=timeout,failure=failure),tempfile.TemporaryDirectory() as d:
                out=Path(d);root=out/'replay/tests'/c.ID;(root/'work').mkdir(parents=True)
                abort=threading.Event();outcome=(code,2.5,timeout,failure)
                original=lambda *a:outcome
                engine=SimpleNamespace(_run_monitored=original,FAIL_RE=c.common.BAD)
                ledger={'simv':'/frozen/simv'}
                with self.assertRaisesRegex(ValueError,'generic postcheck'),r.hooks(engine,out,ledger,abort):
                    engine._run_monitored(r.command_for(root,ledger['simv']),root/'work',root/'console.log',
                        r.TIMEOUT,abort)
                    raise ValueError('generic postcheck')
                receipt=c.read(root/'child_outcome.unvalidated.json')
                self.assertEqual(receipt['returncode'],code)
                self.assertIs(type(receipt['returncode']),int)
                self.assertFalse(receipt['architectural_acceptance'])
                self.assertEqual(receipt['timed_out'],timeout)
                self.assertEqual(receipt['failure_seen'],failure)
                self.assertEqual(abort.is_set(),code!=0 or timeout or failure)
                self.assertIs(engine._run_monitored,original)

    def test_bool_rc_timeout_failure_cannot_pass(self):
        with self.assertRaises(ValueError):r.numeric_gate((False,1,False,False))
        self.assertFalse(r.numeric_gate((17,1,False,False)))
        self.assertFalse(r.numeric_gate((0,1,True,False)))
        self.assertFalse(r.numeric_gate((0,1,False,True)))
        self.assertFalse(r.numeric_gate((0,r.TIMEOUT+1,False,False)))

    def test_private_command_source_runtime_and_cancel(self):
        for change in ('preload','testcase','cwd','cancel','budget'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                out=Path(d);root=out/'replay/tests'/c.ID;(root/'work').mkdir(parents=True)
                abort=threading.Event();called=[]
                engine=SimpleNamespace(_run_monitored=lambda *a:called.append(a),FAIL_RE=c.common.BAD)
                command=r.command_for(root,'/frozen/simv');cwd=root/'work';cancel=abort;budget=r.TIMEOUT
                if change=='preload':command[4]='+PRELOAD='+str(c.REF/'soc/input.elf')
                if change=='testcase':command[5]='+TESTCASE='+c.SOURCE
                if change=='cwd':cwd=out
                if change=='cancel':cancel=threading.Event()
                if change=='budget':budget+=1
                with r.hooks(engine,out,{'simv':'/frozen/simv'},abort),self.assertRaises(ValueError):
                    engine._run_monitored(command,cwd,root/'console.log',budget,cancel)
                self.assertEqual(called,[])
                self.assertFalse((root/'child_outcome.unvalidated.json').exists())

    def test_cpu_cycle_and_bytes_growth_same_generation(self):
        a=dict(pid=123,generation='100',command=['/frozen/simv'],ticks=1,bytes=100,cycle=1)
        b=dict(a,ticks=2,bytes=200,cycle=2)
        self.assertTrue(r.growth(a,b))
        for key in ('ticks','bytes','cycle'):
            self.assertFalse(r.growth(dict(a,**{key:0}),b))
            self.assertFalse(r.growth(a,dict(b,**{key:a[key]})))
        self.assertFalse(r.growth(a,dict(b,generation='101')))
        self.assertFalse(r.growth(a,dict(b,pid=124)))

    def test_completed_csv_line_not_partial(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'trace.csv'
            path.write_bytes(b'cycle,event\n1,retire\n32,retire')
            self.assertEqual(r.last_cycle(path),1)
            path.write_bytes(b'cycle,event\n1,retire\n32,retire\n')
            self.assertEqual(r.last_cycle(path),32)

    def test_source_only_review_cannot_authorize_runtime(self):
        with self.assertRaises((KeyError,ValueError)):
            r.entry_gate(r.SOFTWARE_REVIEW,c.sha(r.SOFTWARE_REVIEW),'fake-plan')

    def test_markers_failure_after_success_veto(self):
        text='\n'.join(['BOARD_CASE_BEGIN '+c.ID,c.SUMMARY,'MACC_PREFIX_PASS '+c.ID+' trials=482',
            'BOARD_CASE_PASS '+c.ID,'BOARD_REPLAY_PASS',c.common.SUCCESS,'$finish'])+'\n'
        c.console_gate(text)
        for marker in ('MACC_OPT_RNG_FAIL','BOARD_CASE_FAIL','FATAL','ABORTED','UNSUPPORTED','ERROR'):
            with self.subTest(marker=marker),self.assertRaises(ValueError):c.console_gate(text+marker+'\n')


if __name__=='__main__':unittest.main()
