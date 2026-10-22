"""Real frozen lifecycle validator and actual numeric-first runner witnesses."""
import copy
import csv
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.dont_write_bytecode=True
import replay
from replay import checker as c
from newscope import *

def protocol_fixture(spec):
    rows=[];offloads=[];cycle=order=arch=0
    routine=spec['routines'][0]
    for r in routine:
        ins=int(r['insn'],16)
        def item(event,ordinal):
            nonlocal cycle
            row=dict(cycle=str(cycle),event=event,order=str(ordinal),port='0',trans_id='0',
                pc=f"{r['pc']:x}",insn=f'{ins:x}',rd='0',rd_wdata='0',mem_addr='0',
                mem_rmask='0',mem_wmask='0',mem_wdata='0',trap='0')
            cycle+=1;return row
        if c.source.offload(ins):
            backend=c.source.rvv(ins) and not(ins&127==87 and (ins>>12)&7==7)
            offloads.append(dict(pc=r['pc'],insn=ins,backend_required=backend))
            rows += [item('cvx_req',arch),item('arch_start',arch)]
            if backend:rows += [item('uop_alloc',arch),item('uop_done',arch)]
            rows.append(item('cvx_resp',arch));arch+=1
        rows.append(item('retire',order));order+=1
    return rows,dict(retired_offloads=offloads)

class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger,cls.repo,cls.framework=c.common.image_context(IMAGE)
        cls.case=replay.cases()[0];cls.s=c.specification(Path(cls.case['elf']))
    def test_actual_bound_template(self):
        parent,options,_,_=self.framework
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            opts=replay.worker.build_options(options,self.repo,Path(d),self.ledger)
            self.assertEqual((opts.jobs,opts.timeout_s),(1,10800))
        self.assertEqual(replay.worker.NAMES,[NAME]);self.assertIs(replay.worker.checker,c)
        self.assertEqual(replay.worker.TIMEOUT,TIMEOUT)
    def test_real_validator_schema_and_missing_families(self):
        from ara_verify.trace import validate_trace,TraceValidationError
        rows,result=protocol_fixture(self.s)
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            path=Path(d)/'trace.csv'
            def evaluate(data):
                with path.open('w',newline='') as f:
                    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(data)
                return validate_trace(path)
            generic=evaluate(rows);self.assertNotIn('status',generic)
            c.protocol_gate(rows,result,generic)
            for removed in ({'arch_start','uop_alloc','uop_done'},{'uop_alloc','uop_done'}):
                bad=[r for r in rows if r['event'] not in removed]
                generic=evaluate(bad)  # The shared validator deliberately permits absent families.
                with self.assertRaises(ValueError):c.protocol_gate(bad,result,generic)
            first=next(r['order'] for r in rows if r['event']=='uop_alloc')
            bad=[r for r in rows if not(r['order']==first and r['event'] in ('uop_alloc','uop_done'))]
            generic=evaluate(bad)
            with self.assertRaisesRegex(ValueError,'Missing entire backend'):c.protocol_gate(bad,result,generic)
            for fault in ('unknown','unmatched','exception','drop_complete_cvx','duplicate','reorder'):
                bad=copy.deepcopy(rows)
                if fault=='unknown':bad[0]['event']='bogus'
                elif fault=='unmatched':next(r for r in bad if r['event']=='uop_done')['port']='9'
                elif fault=='exception':next(r for r in bad if r['event']=='cvx_resp')['trap']='1'
                elif fault=='drop_complete_cvx':bad=[r for r in bad if not(r['order']=='0' and r['event']!='retire')]
                elif fault=='duplicate':bad.insert(2,dict(bad[0]))
                else:
                    requests=[r for r in bad if r['event']=='cvx_req'];requests[0]['insn'],requests[1]['insn']=requests[1]['insn'],requests[0]['insn']
                with self.assertRaises(ValueError):c.protocol_gate(bad,result,evaluate(bad))
    def test_console_actual_ELF_contract(self):
        binary=Path(self.case['elf']).read_bytes()
        text='\n'.join(self.case['pass_markers']+[c.common.SUCCESS,'$finish'])
        c.console_gate(text)
        self.assertNotIn(b'BOARD_CASE_BEGIN',binary)
        for marker in self.case['pass_markers'][1:]:self.assertIn(marker.encode(),binary)
        for bad in (text+'\nFAIL',text+'\n'+MARKER,text.replace('cases=682','cases=681'),text.replace('$finish','')):
            with self.assertRaises(ValueError):c.console_gate(bad)
    def test_terminal_late_abort_and_wrong_scope(self):
        results=[SimpleNamespace(name=NAME,status='PASS',returncode=0,elapsed_s=1.0,reason='')]
        meta=dict(status='COMPLETE',tests=NAMES,status_counts={'PASS':1},completed_at='Host only',jobs=1,
                  timeout_s=TIMEOUT,seed=1,simv=self.ledger['simv'],commit_trace=True,code_coverage=False)
        replay.worker.terminal_gate(results,meta,threading.Event(),self.ledger)
        abort=threading.Event();abort.set()
        with self.assertRaises(ValueError):replay.worker.terminal_gate(results,meta,abort,self.ledger)
        for bad in ([],results*2):
            with self.assertRaises(ValueError):replay.worker.terminal_gate(bad,meta,threading.Event(),self.ledger)
        with tempfile.TemporaryDirectory(dir=HERE) as d:
            out=Path(d);f=out/'plan.json';f.write_text('{}');digest=c.sha(f);f.write_text('{"drift":1}')
            with self.assertRaisesRegex(ValueError,'Late disk plan drift'):replay.terminal_plan_gate(out,digest,IMAGE)
            terminal=dict(status=PASS);c.common.publish(out,terminal,abort)
            self.assertNotEqual(c.read(out/'complete.json')['status'],PASS)
    def test_actual_frozen_parent_monitor_before_early_postcheck0_17(self):
        parent,options,testcase,_=self.framework
        import ara_verify.runner as engine
        for code in (0,17):
            with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                out=Path(tmp);root=out/'replay/tests'/NAME;(root/'work').mkdir(parents=True)
                (root/'input.elf').write_bytes(b'Host only')
                opts=replay.worker.build_options(options,self.repo,out,self.ledger)
                abort=threading.Event()
                runner=replay.worker.checked_runner(parent,abort,lambda r:None,lambda n:None)(opts,[],[])
                runner._suite_frozen=True;runner._frozen_binaries[NAME]='Host only hash'
                def monitored(command,cwd,console,timeout,cancel_event=None):
                    Path(console).write_text(c.common.SUCCESS);(Path(cwd)/'run.vcs.log').write_text(c.common.SUCCESS)
                    (root/'commit_trace.csv').write_text('Host only')
                    if code==17:(root/'command.json').write_text('invalid metadata')
                    return(code,1.0,False,False)
                test=testcase(NAME,'app','',Path(self.case['elf']),NAME,TIMEOUT)
                with patch.object(engine,'simulation_image',return_value={}),patch.object(engine,'_run_monitored',monitored),\
                     patch.object(engine,'validate_trace',return_value={}),\
                     patch.object(engine,'check_inputs',side_effect=RuntimeError('actual_parent_early_postcheck')):
                    with replay.worker.engine_hooks(engine,abort,{NAME:root},self.ledger['simv']):
                        with self.assertRaises(RuntimeError if code==0 else ValueError):runner._run_test(test,Path(self.ledger['simv']))
                receipt=c.read(root/'child_outcome.unvalidated.json')
                self.assertEqual(receipt['returncode'],code);self.assertEqual(receipt['source_label'],HISTORICAL)
                self.assertFalse(receipt['architectural_acceptance'])
                self.assertEqual(c.read(out/'first_cause.json')['returncode'],code);self.assertTrue(abort.is_set())

    def test_timeout_negative_preserved_before_metadata(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root=Path(tmp)/NAME;(root/'work').mkdir(parents=True)
            command=replay.worker.monitor_command(root,self.ledger['simv'],NAME)
            (root/'command.json').write_text('invalid metadata')
            abort=threading.Event();wrapped=replay.monitored(lambda *a:(-9,10800.0,True,False),abort,{NAME:root},self.ledger['simv'])
            with self.assertRaises(ValueError):wrapped(command,root/'work',root/'console.log',TIMEOUT)
            self.assertEqual(c.read(root/'child_outcome.unvalidated.json')['returncode'],-9)
            self.assertEqual(c.read(root/'first_cause.json')['kind'],'MONITOR_OUTCOME')

    def test_budget_resources(self):
        self.assertEqual((JOBS,TIMEOUT,OUTER),(1,10800,13200))
        c.common.resource_math([],32*1024**3,HERE,1,0)
        with self.assertRaises(ValueError):c.common.resource_math([],31*1024**3,HERE,1,0)
        with self.assertRaises(ValueError):replay.authorization_gate('0'*64,None,None)

if __name__=='__main__':
    started=time.monotonic();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WorkerTests))
    paths=[HERE/f for f in ('newscope.py','model.py','elf.py','strict.py','checker.py','replay.py','test_worker.py')]
    replay.durable(HERE/replay.HOST_REPORT,dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),elapsed_s=time.monotonic()-started,
        pins={str(p):c.sha(p) for p in paths},real_validator=True,DUT_started=False))
    raise SystemExit(not result.wasSuccessful())
