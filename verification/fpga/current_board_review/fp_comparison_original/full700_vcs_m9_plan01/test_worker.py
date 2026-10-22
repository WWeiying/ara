"""Reuse mature real-parent numeric/protocol tests; only changed scope/diagnostics."""
import importlib.util
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode=True
import replay
from replay import checker as c
from newscope import *

_spec=importlib.util.spec_from_file_location('immutable_worker_tests700',PREVIOUS/'test_worker.py')
old=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(old)


class Tests(old.WorkerTests):
    def test_review_actual_file_gate(self):
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            path=Path(d)/'synthetic_entry.json'
            entry=dict(decision='NO_BLOCKER_ENTRY_ORIGINAL700_M9',no_blocker=True,
                       plan_sha256='a'*64,worker_sha256=c.sha(HERE/'replay.py'),
                       checker_sha256=c.sha(HERE/'checker.py'),ready_sha256=READY_SHA,pins={})
            replay.durable(path,entry)
            with patch.object(replay,'ENTRY',path):
                replay.authorization_gate('a'*64,path,c.sha(path))
                with self.assertRaises(ValueError):replay.authorization_gate('a'*64,path,'b'*64)
                with self.assertRaises(ValueError):replay.authorization_gate('b'*64,path,c.sha(path))
                with self.assertRaises(ValueError):replay.authorization_gate('a'*64,HERE/'USER_AUTHORIZATION.md',c.sha(HERE/'USER_AUTHORIZATION.md'))
                for key in ('no_blocker','worker_sha256','checker_sha256','ready_sha256','decision'):
                    bad=Path(d)/(key+'.json')
                    replay.durable(bad,dict(entry,**{key:False if key=='no_blocker' else 'b'*64}))
                    with patch.object(replay,'ENTRY',bad):
                        with self.assertRaises(ValueError):replay.authorization_gate('a'*64,bad,c.sha(bad))

    def test_actual_bound_template(self):
        _,options,_,_=self.framework
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            opts=replay.worker.build_options(options,self.repo,Path(d),self.ledger)
            self.assertEqual((opts.jobs,opts.timeout_s),(1,7200))
        self.assertEqual(replay.worker.NAMES,[NAME]);self.assertIs(replay.worker.checker,c)
        self.assertEqual(replay.worker.TIMEOUT,TIMEOUT)

    def test_console_actual_ELF_contract(self):
        binary=Path(self.case['elf']).read_bytes()
        text='\n'.join(self.case['pass_markers']+[c.common.SUCCESS,'$finish'])
        c.console_gate(text)
        self.assertNotIn(b'BOARD_CASE_BEGIN',binary)
        for marker in self.case['pass_markers'][1:]:self.assertIn(marker.encode(),binary)
        for bad in (text+'\nFAIL',text+'\n'+MARKER,text.replace('cases=700','cases=699'),text.replace('$finish','')):
            with self.assertRaises(ValueError):c.console_gate(bad)

    def test_timeout_negative_preserved_before_metadata(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root=Path(tmp)/NAME;(root/'work').mkdir(parents=True)
            cmd=replay.worker.monitor_command(root,self.ledger['simv'],NAME)
            (root/'command.json').write_text('invalid metadata')
            abort=threading.Event()
            wrapped=replay.monitored(lambda *a:(-9,7200.0,True,False),abort,{NAME:root},self.ledger['simv'])
            with self.assertRaises(ValueError):wrapped(cmd,root/'work',root/'console.log',TIMEOUT)
            self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],-9)
            self.assertEqual(c.read(root/'first_cause.json')['kind'],'MONITOR_OUTCOME')

    def test_budget_resources(self):
        self.assertEqual((JOBS,TIMEOUT,OUTER),(1,7200,9000))
        c.common.resource_math([],32*1024**3,HERE,1,0)
        with self.assertRaises(ValueError):c.common.resource_math([],31*1024**3,HERE,1,0)
        with self.assertRaises(ValueError):replay.authorization_gate('0'*64,None,None)

    def test_firstcause_diagnostic_context_only(self):
        # Observer-only boundary, not a substitute for the actual full700 reference.
        import strict
        g=c.model()['rows'][0]
        helper=self.s['routines'][0]
        rows=[dict(pc=helper[0]['pc'],insn=int(helper[0]['insn'],16),cycle=100),
              dict(pc=helper[9]['pc'],insn=int(helper[9]['insn'],16),cycle=101,value=16)]
        def fail(data,*args):
            list(data);raise ValueError('Actual fflags')
        with patch.object(strict._source,'audit',side_effect=fail):
            with self.assertRaises(strict.AuditError) as caught:strict.audit(rows,self.s)
        d=caught.exception.diagnostic
        self.assertEqual((d['call_ordinal'],d['cycle'],d['classification']),(1,101,'fflags'))
        self.assertEqual((d['expected_flags'],d['actual_flags']),(g['flags'],16))
        self.assertEqual(d['pc'],hex(helper[9]['pc']))


if __name__=='__main__':
    start=time.monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    paths=[*HERE.glob('*.py'),PREVIOUS/'test_worker.py',PREVIOUS/'replay.py',PREVIOUS/'checker.py',
           PREVIOUS/'strict.py',PREVIOUS/'elf.py',PREVIOUS/'model.py']
    replay.durable(HERE/replay.HOST_REPORT,dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),elapsed_s=time.monotonic()-start,
        pins={str(p):c.sha(p) for p in paths},real_validator=True,real_frozen_parent=True,
        diagnostic_test_scope='Observer-only context, not full oracle proof',DUT_started=False))
    raise SystemExit(not result.wasSuccessful())
