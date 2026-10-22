#!/usr/bin/env python3
"""Small metadata/outcome/plan tests; never start or query live simulation."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
sys.dont_write_bytecode=True
import replay as app
from replay import checker as c

class Host(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=app.HERE,prefix='host_tmp_');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'work').mkdir()
        self.case,self.spec=app.scope()
        self.ledger=dict(simv='/synthetic/image/simv',files={'synthetic':'host-only'})
        shutil.copyfile(self.case['elf'],self.root/'input.elf')
        (self.root/'console.log').write_text('NF2_REMAINING4_SV39_PASS\n'+c.common.SUCCESS+'\n$finish\n')
        (self.root/'work/run.vcs.log').write_text('host metadata fixture\n')
        (self.root/'commit_trace.csv').write_text('not an architectural CSV\n')
        self.write('trace_summary.json',dict(status='VALID'))
        self.command=dict(cwd=str(self.root/'work'),command=[self.ledger['simv'],'-l','run.vcs.log',
            '+ntb_random_seed=1','+PRELOAD='+str(self.root/'input.elf'),'+TESTCASE='+app.NAME,
            '+NO_FSDB','+COMMIT_TRACE='+str(self.root/'commit_trace.csv')])
        self.write('command.json',self.command)
        self.write('inputs.json',dict(binary=dict(source=self.case['elf'],path=str(self.root/'input.elf'),
                    sha256=self.case['sha256']),simv=dict(path=self.ledger['simv'],image_sha256=self.ledger['files'])))
        self.result=SimpleNamespace(name=app.NAME,status='PASS',returncode=0,elapsed_s=1.5,reason='',artifact_dir=self.root)
    def write(self,name,data):(self.root/name).write_text(json.dumps(data))
    def check(self):c.common.check_artifacts(self.result,c.runtime_case(self.case),self.ledger)
    def test_runtime_vs_history(self):
        original=copy.deepcopy(self.case);self.check();self.assertEqual(original,self.case)
        with self.assertRaisesRegex(ValueError,'Command provenance'):c.common.check_artifacts(self.result,self.case,self.ledger)
        self.case['historical_names'][0]='wrong_source'
        with self.assertRaises(ValueError):self.check()
    def test_wrong_command(self):
        for i,v in ((3,'+ntb_random_seed=2'),(4,'+PRELOAD='+self.case['elf']),(5,'+TESTCASE=historical')):
            bad=copy.deepcopy(self.command);bad['command'][i]=v;self.write('command.json',bad)
            with self.assertRaisesRegex(ValueError,'Command provenance'):self.check()
        self.write('command.json',dict(self.command,cwd=str(self.root)))
        with self.assertRaisesRegex(ValueError,'Command provenance'):self.check()
    def test_raw_veto_missing_oracle_and_elf(self):
        for text in ('NF2_REMAINING4_SV39_FAIL case=2','BOARD_REPLAY_MISMATCH case=1'):
            self.assertTrue(c.VETO.search(text))
        original=(self.root/'console.log').read_text()
        (self.root/'console.log').write_text(c.common.SUCCESS+'\n$finish\n')
        with self.assertRaisesRegex(ValueError,'oracle'):self.check()
        (self.root/'console.log').write_text(original);(self.root/'input.elf').write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'ELF drift'):self.check()
    def test_checkerthrow_durable_outcome(self):
        supplied=self.result
        class Parent:
            def _run_test(self,*_):return supplied
        def throws(_):
            self.assertEqual(c.read(self.root/'child_outcome.unvalidated.json')['returncode'],0)
            raise ValueError('injected postcheck failure')
        abort=threading.Event()
        with self.assertRaisesRegex(ValueError,'injected'):
            app.worker.checked_runner(Parent,abort,throws)()._run_test(None,None)
        result=c.read(self.root/'child_outcome.unvalidated.json')
        self.assertFalse(result['architectural_acceptance']);self.assertTrue(abort.is_set())
        self.assertEqual(result['command_sha256'],c.sha(self.root/'command.json'))
    def test_abort_during_validation(self):
        supplied=self.result
        class Parent:
            def _run_test(self,*_):return supplied
        abort=threading.Event()
        result=app.worker.checked_runner(Parent,abort,lambda _:abort.set())()._run_test(None,None)
        self.assertEqual(result.status,'CANCELLED');self.assertTrue(abort.is_set())
    def test_budget_and_disk_pin(self):
        image=Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image')
        data=dict(status='PREPARED_NOT_RUN',image=str(image),image_sha256=app.IMAGE_SHA,case=self.case,spec=self.spec,
                  timeout_s=6300,service_timeout_s=6900,jobs=1,unit=app.UNIT,no_build=True,no_retry=True,
                  no_fsdb=True,reference_ready_sha256=app.READY_SHA,independent_reference_pins=app.AUDIT_PINS,
                  pins={str(Path(app.__file__)):c.sha(Path(app.__file__))})
        app.validate(data,image)
        for key,value in (('jobs',2),('timeout_s',9000),('service_timeout_s',10800),('no_fsdb',False)):
            bad=copy.deepcopy(data);bad[key]=value
            with self.assertRaises(ValueError):app.validate(bad,image)
        bad=copy.deepcopy(data);bad['pins'][str(Path(app.__file__))]='0'*64
        with self.assertRaises(ValueError):app.validate(bad,image)
    def test_actual_code_map_reject(self):
        from test_csv import synthetic
        rows=synthetic(self.spec['symbols'])
        observer=c.csv_check.Checker(self.spec['symbols'],self.spec['code'])
        row=dict(rows[0],pc=hex(self.spec['symbols']['mx_segment_load'])[2:],insn='22055c07')
        with self.assertRaisesRegex(ValueError,'PC/code'):observer.row(row)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    c.require(not args.out.exists(),'Fresh Host output only')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins={str(p):c.sha(p) for p in (Path(__file__),Path(app.__file__),Path(c.__file__),Path(c.csv_check.__file__),
                                  Path(app.outcome.__file__),Path(app.worker.__file__))}
    c.common.save(args.out,dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),pins=pins))
    raise SystemExit(not result.wasSuccessful())
