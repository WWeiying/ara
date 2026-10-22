#!/usr/bin/env python3
"""Bounded delta tests; preserve Host01 failure evidence, no DUT/Spike/live query."""
import ast
from dataclasses import replace
import inspect
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import sys
sys.dont_write_bytecode=True
import test_host as old
from test_host import replay,c


class Delta(old.Gates):
    checks=[]

    def test_inherited_evidence_and_exact_code_delta(self):
        self.assertEqual(c.sha(c.HERE/'host01.json'),'e6d18fa184cf6b9c920c7c2e6d73dcb29e63b4ff55e737ce0fc633f30d1d9024')
        self.assertEqual(c.sha(c.HERE/'host01.log'),'ad0098ab5622dc6f3f8379bed9acfad32b296012df67c4777ebe89c9c85a3343')
        h=c.read(c.HERE/'host01.json')
        self.assertEqual((h['status'],h['test_methods'],h['checks'],h['failures']),('HOST_FAIL',17,548,2))
        self.assertEqual(c.sha(c.HERE/'checker.py'),h['checker_sha256'])
        self.assertEqual(c.sha(c.HERE/'test_host.py'),h['script_sha256'])
        before=c.HERE/'replay_before_host01.py'
        self.assertEqual(c.sha(before),h['runner_sha256'])
        a={n.name:n for n in ast.parse(before.read_text()).body if isinstance(n,ast.FunctionDef)}
        b={n.name:n for n in ast.parse((c.HERE/'replay.py').read_text()).body if isinstance(n,ast.FunctionDef)}
        changed={'prepare','mf4_gate','run'}
        self.assertEqual(set(b)-set(a),{'build_options','quiesce_deadline'})
        for name in set(a)-changed:self.assertEqual(ast.dump(a[name]),ast.dump(b[name]),name)
        source=ast.get_source_segment(before.read_text(),a['run'])
        expected=source.replace("opts=options(repo,out/'replay','default',1,JOBS,False,False,True,Path(ledger['simv']),True,TIMEOUT)",
                                'opts=build_options(options,repo,out,ledger)')
        expected=expected.replace('        finally:\n','        finally:\n            quiesce_deadline(timer,abort,deadline)\n')
        expected=expected.replace('common.publish(out,terminal,abort);timer.cancel()','common.publish(out,terminal,abort)')
        self.assertEqual(ast.dump(ast.parse(expected).body[0]),ast.dump(b['run']))
        log=(c.HERE/'host01.log').read_text()
        self.assertEqual(log.count("name='duplicate_op0_entry'"),2)
        self.assertEqual(log.count('does not match "Duplicate RVV retirement"'),2)
        self.record('exact_inheritance_and_only_declared_runtime_delta')

    def test_duplicate_entry_actual_rejection_both_widths(self):
        for shape in ('e16_m8','e32_mf2'):
            s=self.specs[shape]
            with self.assertRaisesRegex(ValueError,'Duplicate RVV retirement'):
                c.retirement(self.injected(s,s['routine'][0]),s)
            self.record(shape+':corrected_duplicate_entry_diagnostic')

    def test_actual_frozen_RunOptions_and_command_no_simulation(self):
        ledger,repo,(parent,options,testcase,_)=c.common.image_context(replay.IMAGE)
        import ara_verify.runner as engine
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            out=Path(tmp);opts=replay.build_options(options,repo,out,ledger)
            self.assertEqual((opts.jobs,opts.seed,opts.timeout_s),(3,1,5400))
            self.assertFalse(opts.dry_run);self.assertFalse(opts.build_only);self.assertTrue(opts.skip_build)
            self.assertTrue(opts.commit_trace);self.assertFalse(opts.code_coverage)
            case=replay.scope()[0];test=testcase(case['id'],'app','',Path(case['elf']),case['id'],5400)
            dry=replace(opts,dry_run=True)
            with patch.object(engine,'_run_monitored',side_effect=AssertionError('No process allowed')):
                runner=parent(dry,[test],['HOST_ONLY'])
                result=runner._run_test(test,Path(ledger['simv']))
            self.assertEqual(result.status,'DRY_RUN')
            command=c.read(result.artifact_dir/'command.json')['command']
            self.assertEqual(command,[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
                '+PRELOAD='+case['elf'],'+TESTCASE='+case['id'],'+NO_FSDB',
                '+COMMIT_TRACE='+str(result.artifact_dir/'commit_trace.csv')])
        self.record('actual_RunOptions_jobs3_seed1_and_frozen_command')

    def test_real_Timer_old_publish_race_reproduced(self):
        abort=threading.Event();release=threading.Event();fired=threading.Event();calls=0
        def callback():
            if release.wait(3):abort.set();fired.set()
        timer=threading.Timer(0,callback);timer.start()
        def pending():
            nonlocal calls
            calls+=1
            if calls==2:
                release.set();self.assertTrue(fired.wait(3))
            return set()
        try:
            with tempfile.TemporaryDirectory(dir=c.HERE) as tmp,patch.object(c.common.signal,'sigpending',side_effect=pending):
                terminal=dict(status=replay.PASS)
                c.common.publish(Path(tmp),terminal,abort)
                actual=c.read(Path(tmp)/'complete.json')
                self.assertTrue(abort.is_set());self.assertEqual(actual['status'],replay.PASS)
                c.common.save(c.HERE/'host02_timer_before.json',dict(status='HOST_ONLY_RACE_REPRODUCED_NOT_DUT',
                    event_set=True,published=actual,gate_calls=calls))
        finally:release.set();timer.join()
        self.record('real_Timer_final_gate_race_reproduced')

    def test_quiesce_joins_callback_and_preserves_abort(self):
        abort=threading.Event();entered=threading.Event();release=threading.Event()
        def callback():
            entered.set()
            if release.wait(3):abort.set()
        timer=threading.Timer(0,callback);timer.start();self.assertTrue(entered.wait(3))
        releaser=threading.Timer(.02,release.set);releaser.start()
        try:replay.quiesce_deadline(timer,abort,time.monotonic()+100)
        finally:release.set();timer.join();releaser.join()
        self.assertFalse(timer.is_alive());self.assertTrue(abort.is_set())
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            terminal=dict(status=replay.PASS);c.common.publish(Path(tmp),terminal,abort)
            self.assertEqual(c.read(Path(tmp)/'complete.json')['status'],'NOT_PASS')
        self.record('quiesce_join_pending_callback_NO_PASS')

    def test_quiesce_deadline_reached_and_nonexpired(self):
        for now,aborted in ((20,True),(9,False)):
            abort=threading.Event();timer=threading.Timer(100,abort.set);timer.start()
            with patch.object(replay.time,'monotonic',return_value=now):replay.quiesce_deadline(timer,abort,10)
            self.assertEqual(abort.is_set(),aborted);self.assertFalse(timer.is_alive())
            self.record('deadline_latched:'+str(aborted))

    def test_mf4_actual_report_audit_terminal_required(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as tmp:
            root=Path(tmp);cp=root/'complete.json';report=root/'REVIEW.md';audit=root/'result.json';path=root/'proof.json'
            report.write_text('SYNTHETIC HOST ONLY, NOT ACCEPTANCE')
            evidence=root/'raw';evidence.write_text('HOST')
            complete=dict(status='PASS_M6_ORIGINAL_E16_MF4_SINGLE144_NOT_FULL_PARENT',plan_sha256=replay.MF4_PLAN_SHA,
                aborted=False,pins_unchanged=True,results=[dict(name='original_e16_mf4',status='PASS',returncode=0,reason='',elapsed_s=1)],
                evidence_pins={str(evidence):c.sha(evidence)})
            c.common.save(cp,complete)
            actual=dict(status=replay.MF4_STATUS,plan_sha256=replay.MF4_PLAN_SHA,complete_sha256=c.sha(cp),image_sha256='image')
            c.common.save(audit,actual)
            proof=dict(status=replay.MF4_STATUS,plan_sha256=replay.MF4_PLAN_SHA,soc_elf_sha256=replay.MF4_ELF_SHA,
                image_sha256='image',complete_path=str(cp),complete_sha256=c.sha(cp),report_path=str(report),report_sha256=c.sha(report),
                audit_path=str(audit),audit_sha256=c.sha(audit),audit_status=replay.MF4_STATUS,
                evidence_pins={str(p):c.sha(p) for p in (report,audit,cp,evidence)})
            c.common.save(path,proof);replay.mf4_gate(path,c.sha(path),'image')
            for key,value in [('status','INDEPENDENT_REFERENCE_ALL9_ACCEPTED_NOT_DUT'),('image_sha256','wrong'),
                    ('report_sha256','wrong'),('audit_status','PASS'),('evidence_pins',{})]:
                c.common.save(path,dict(proof,**{key:value}))
                with self.assertRaises(ValueError):replay.mf4_gate(path,c.sha(path),'image')
                self.record('actual_mf4_gate:'+key)
            c.common.save(audit,dict(actual,complete_sha256='wrong'))
            altered=copy_dict(proof,audit_sha256=c.sha(audit));altered['evidence_pins']=dict(proof['evidence_pins'],**{str(audit):c.sha(audit)})
            c.common.save(path,altered)
            with self.assertRaises(ValueError):replay.mf4_gate(path,c.sha(path),'image')
            self.record('actual_mf4_audit_terminal_disagreement')


def copy_dict(d,**kw):return dict(d,**kw)


if __name__=='__main__':
    if (c.HERE/'host02.json').exists():raise SystemExit('Preserve existing delta results')
    names=['test_inherited_evidence_and_exact_code_delta','test_duplicate_entry_actual_rejection_both_widths',
        'test_actual_frozen_RunOptions_and_command_no_simulation','test_real_Timer_old_publish_race_reproduced',
        'test_quiesce_joins_callback_and_preserves_abort','test_quiesce_deadline_reached_and_nonexpired',
        'test_mf4_actual_report_audit_terminal_required','test_plan_image_ELF_and_budget_drift',
        'test_fresh_terminal_disk','test_COMPLETE_exact9_and_noabort','test_failure_cancel_lateabort_validationexception',
        'test_sticky_cancel_stops_new_dispatch','test_noabort_atomic_publish','test_owner_and_deadline_no_budget_extension',
        'test_parent_authorization_must_bind_gate']
    with (c.HERE/'host02.log').open('x') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.TestSuite(Delta(n) for n in names))
    c.common.save(c.HERE/'host02.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'HOST_FAIL',
        test_methods=result.testsRun,checks=len(Delta.checks),check_names=Delta.checks,
        failures=len(result.failures)+len(result.errors),shapes=c.SHAPES,
        inherited_host01_sha256=c.sha(c.HERE/'host01.json'),inherited_status='HOST_FAIL_TWO_DIAGNOSTIC_ASSERTIONS_CORRECTED_BY_HOST02',
        checker_unchanged_from_host01=True,script_sha256=c.sha(Path(__file__)),checker_sha256=c.sha(c.HERE/'checker.py'),
        runner_sha256=c.sha(c.HERE/'replay.py'),live_queries=False,DUT_started=False,reference_started=False))
    print(json.dumps({k:v for k,v in c.read(c.HERE/'host02.json').items() if k!='check_names'}),flush=True)
    raise SystemExit(not result.wasSuccessful())
