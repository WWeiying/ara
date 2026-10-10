#!/usr/bin/env python3
import argparse
import copy
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'verification/coverage'))
sys.path.insert(0,str(ROOT/'verification'))
import audit_gap71_custom as audit
import run_gap71_custom_checked_extension as adapter
PREFLIGHT=None

class OracleTests(unittest.TestCase):
    def test_pages(self):
        p=audit.pages(0x80040000,False,False)
        self.assertEqual(p[2][:3],[0x20010c43,0x20011443,0x20011043]);self.assertEqual(p[0][2],0x200000cf)
        self.assertEqual(audit.pages(0x80040000,True,True)[2][2],0)
    def test_qbs_numeric(self):
        self.assertEqual(sum(i%7-3 for i in range(256)),-6)
        self.assertEqual(audit.outputs('gap71_qbs_read')[0][128:144],[0xc0c00000]+[0]*15)
    def test_akv_copy(self):
        rows=audit.outputs('gap71_akv_read');self.assertEqual(rows[:3],rows[3:]);self.assertNotEqual(rows[0],rows[1])
    def test_fault_no_commit(self):
        for name in ('gap71_qbs_fault','gap71_akv_fault'):self.assertEqual(audit.outputs(name)[0],[audit.seed(i) for i in range(512)])
    def test_count(self):
        self.assertEqual([audit.checks(n) for n in audit.CASE_NAMES],[140,144,268,208])
    def test_log_negative(self):
        for n in audit.CASE_NAMES:
            log='GAP71 %s backend=custom-dut snapshots=%d digest=%016x traps=%d\nPASSED: %s checks=%d errors=0\n'%(n,audit.ns(n),audit.digest(w for p in audit.outputs(n) for w in p),1+n.endswith('_fault'),n,audit.checks(n))
            audit.validate_log(log,n,'custom-dut')
            for changed in (log.replace('errors=0','errors=1'),log.replace('custom-dut','software-reference'),log+log,log.replace('digest=','digest=0')):
                with self.assertRaises(ValueError):audit.validate_log(changed,n,'custom-dut')
    def test_identity(self):
        self.assertIsInstance(adapter.CASE_NAMES,list)
        self.assertEqual(adapter.CASE_NAMES,['app:'+n for n in audit.CASE_NAMES])
        with self.assertRaises(ValueError):audit.modes('qbs_gap71_read')
    def test_bounded_command(self):
        cmd=['real-wrapper','+TESTCASE=gap71_qbs_read','+NO_FSDB'];work=Path('/tmp/gap71')
        self.assertEqual(adapter.perf_command(cmd,'gap71_qbs_read',work)[-2:],['+QBS_PERF','+VECTOR_TRACE=/tmp/gap71/vector_trace.csv'])
        for changed in (cmd[:-1],cmd+['+AKV_PERF'],cmd+['+VECTOR_TRACE=/tmp/foreign']):
            with self.assertRaises(ValueError):adapter.perf_command(changed,'gap71_qbs_read',work)
    def test_install_preserves_script(self):
        prior=adapter.checked.SCRIPT;adapter.install_hooks();a=adapter.install_hooks();self.assertIs(a,adapter.install_hooks());self.assertEqual(adapter.checked.SCRIPT,prior)
    def test_reject_failed_runtime(self):
        for n in audit.CASE_NAMES:
            with self.assertRaises((ValueError,KeyError)):adapter.runtime_proof(ROOT,{'checked_extension':adapter.checked.VERSION,'cases':[]},{'name':n,'status':'FAIL'})
    def test_runtime_file_boundary(self):
        target=Path('/tmp/gap71/results/gap71_qbs_read');vdb=target/'tests/app_gap71_qbs_read/work/code.vdb'
        p=str(target/'summary.json');d=str(vdb/'native.xml');old='/tmp/history/ledger.json';unbound=str(target/'unbound.csv')
        proof=SimpleNamespace(files={p:'a',d:'b',old:'c',unbound:'d'})
        row=dict(files={p:'a',old:'c'},vdb=str(vdb),vdb_files={d:'b'})
        self.assertEqual(adapter.runtime_files(proof,row,target),{p:'a',d:'b'})
        row['files'][p]='wrong';self.assertEqual(adapter.runtime_files(proof,row,target),{d:'b'})
    def test_runtime_trace_empty_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix='gap71-unit-') as d:
            p=Path(d)/'trace.csv';p.write_text('cycle,event,insn,pc,trans_id,trap\n')
            with self.assertRaises((ValueError,KeyError)):
                audit.runtime_traces(p,p,'gap71_qbs_read',dict(symbols={},words={}))
    def test_perf_strict_translation(self):
        row='[QBS_PERF] success=1 fault=0 validation_fault=0 read_fault=0 translations=3 read_ranges=3 payload_bytes=452\n'
        self.assertEqual(audit.runtime_perf(row*2,'gap71_qbs_read')['commands'],2)
        for text in (row,row*3,(row*2).replace('translations=3','translations=0'),(row*2).replace('read_fault=0','read_fault=2')):
            with self.assertRaises(ValueError):audit.runtime_perf(text,'gap71_qbs_read')

@unittest.skipUnless(PREFLIGHT,'real build not supplied')
class RealTraceTests(unittest.TestCase):
    def test_real_trace(self):
        d=json.loads((PREFLIGHT/'execution-proof.json').read_text())
        for n,r in d.items():
            text=Path(r['trace_log']).read_text();self.assertEqual(audit.spike_trace(text,n,r['spike']['metadata']),r['trace'])
            with self.assertRaises(ValueError):audit.spike_trace(text.replace('trap_supervisor_ecall','trap_illegal_instruction'),n,r['spike']['metadata'])
    def test_real_log(self):
        for n,r in json.loads((PREFLIGHT/'execution-proof.json').read_text()).items():
            log=Path(r['stdout']).read_text();audit.validate_log(log,n,'software-reference')
            with self.assertRaises(ValueError):audit.validate_log(log,n,'custom-dut')
    def test_real_elf(self):
        for n,r in json.loads((PREFLIGHT/'execution-proof.json').read_text()).items():
            obj=json.loads((PREFLIGHT/(n+'.dut.metadata.log')).read_text())[0];blob=Path(r['dut']['elf']).read_bytes()
            self.assertEqual(audit.metadata(obj,blob,n,False),r['dut']['metadata'])
            damaged=copy.deepcopy(obj)
            for x in damaged['Symbols']:
                if x['Symbol']['Name']['Name']=='gap71_site':x['Symbol']['Value']+=4
            with self.assertRaises(ValueError):audit.metadata(damaged,blob,n,False)

if __name__=='__main__':
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--preflight',type=Path)
    args,remaining=p.parse_known_args();PREFLIGHT=args.preflight
    # Decorator is evaluated before CLI parsing.
    RealTraceTests.__unittest_skip__=PREFLIGHT is None
    unittest.main(argv=[sys.argv[0],*remaining])
