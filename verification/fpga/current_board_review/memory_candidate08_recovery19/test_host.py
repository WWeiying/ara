#!/usr/bin/env python3
"""Focused wrapper negatives; no DUT, golden replay, or old CSV parsing."""
import csv
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
import worker as w


class Tests(unittest.TestCase):
    def receipt(self):
        return dict(returncode=0,elapsed_s=1.0,timed_out=False,failure_seen=False,abort_set=False)

    def test_numeric_zero(self):
        w.check_receipt(self.receipt(),180)

    def test_bad_exit(self):
        for rc in (False,True,None,'0',1,-15):
            with self.subTest(rc=rc), self.assertRaises(ValueError):
                w.check_receipt(dict(self.receipt(),returncode=rc),180)

    def test_incomplete_or_aborted(self):
        for field in ('timed_out','failure_seen','abort_set'):
            for value in (True,None,0):
                with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                    w.check_receipt(dict(self.receipt(),**{field:value}),180)

    def test_budget(self):
        for elapsed in (-1,181,True,float('nan'),float('inf')):
            with self.subTest(elapsed=elapsed), self.assertRaises(ValueError):
                w.check_receipt(dict(self.receipt(),elapsed_s=elapsed),180)

    def files(self):
        old = {w.ADDRGEN:'old', **{'file%d'%i:'same' for i in range(538)}}
        return old, dict(old,**{w.ADDRGEN:w.ADDRGEN_SHA})

    def test_exact_delta(self):
        w.check_delta(*self.files())

    def test_bad_delta(self):
        old,new = self.files()
        for bad in (old,dict(new,alien='x'),dict(new,file1='bad'),dict(new,**{w.ADDRGEN:'other'})):
            with self.subTest(), self.assertRaises(ValueError): w.check_delta(old,bad)

    def test_only_exact_helper_root_relocation(self):
        old,new=self.files()
        for n in ('frozen.filelist','hardware/bender'):
            old.pop('file'+str(536 if n=='frozen.filelist' else 537))
            new.pop('file'+str(536 if n=='frozen.filelist' else 537))
            old[n]='old';new[n]='new'
        relocation={n:(b'/M7/frozen/x',b'/M8/frozen/x',b'/M7',b'/M8')
                    for n in ('frozen.filelist','hardware/bender')}
        w.check_delta(old,new,relocation)
        relocation['hardware/bender']=(b'/M7/frozen/x',b'/M8/frozen/y',b'/M7',b'/M8')
        with self.assertRaises(ValueError):w.check_delta(old,new,relocation)

    def test_terminal_membership(self):
        cases=[{'id':'one'}]
        result=SimpleNamespace(name='one',status='PASS',returncode=0)
        w.terminal_ok([result],cases,threading.Event())
        for bad in ([],[result,result],[SimpleNamespace(name='alien',status='PASS',returncode=0)],
                    [SimpleNamespace(name='one',status='PASS',returncode=False)],
                    [SimpleNamespace(name='one',status='ERROR',returncode=0)]):
            with self.subTest(), self.assertRaises(ValueError): w.terminal_ok(bad,cases,threading.Event())
        abort=threading.Event();abort.set()
        with self.assertRaises(ValueError): w.terminal_ok([result],cases,abort)

    def test_complete_csv_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            a=root/'a.csv'; b=root/'b.csv'
            a.write_text('cycle,event,order,rd_wdata\n1,retire,0,11\n2,retire,1,22\n')
            b.write_text('cycle,event,order,rd_wdata\n2,retire,0,11\n3,retire,1,22\n')
            result=w.m7.compare_cycles(a,b,root/'diff.csv')
            self.assertEqual((result['rows'],result['cycle_changed_rows'],result['last_cycle_delta']),(2,2,1))
            b.write_text('cycle,event,order,rd_wdata\n2,retire,0,11\n3,retire,1,23\n')
            with self.assertRaises(ValueError): w.m7.compare_cycles(a,b,root/'bad.csv')
            b.write_text('cycle,event,order,rd_wdata\n2,retire,0,11\n')
            with self.assertRaises(ValueError): w.m7.compare_cycles(a,b,root/'partial.csv')

    def test_exclusive_terminal(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'complete.json'
            w.save(p,{'status':'NOT_PASS'})
            with self.assertRaises(FileExistsError): w.save(p,{'status':'PASS'})
            self.assertEqual(w.read(p),{'status':'NOT_PASS'})

    def test_checker_error_with_zero_parser_exit(self):
        good=dict(status='CSV_FULL_ORACLE_PASS',checks=5215,rounds=50,backing_words_read=32768,
                  pte_words_read=1536,repairs=0,retries=0)
        w.check_csv_result('resident',good)
        for change in ({'status':'CSV_NOT_PASS'},{'checks':5214},{'rounds':49},{'repairs':1},
                       {'retries':1},{'backing_words_read':32767},{'pte_words_read':1535}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                w.check_csv_result('resident',dict(good,**change))
        for kind, status, count in (('indexed','INDEXED_PREFIX_CSV_PASS',966),
                                   ('load','MASK_DRAIN_CSV_PASS',914),('store','MASK_DRAIN_CSV_PASS',914)):
            w.check_csv_result(kind,dict(status=status,checks=count))
            with self.assertRaises(ValueError): w.check_csv_result(kind,dict(status=status,checks=count-1))


if __name__ == '__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    w.save(w.HERE/'host02.json',dict(passed=result.wasSuccessful(),tests=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),worker_sha256=w.sha(w.HERE/'worker.py'),
        tests_sha256=w.sha(Path(__file__)),checker_adapter_sha256=w.sha(w.HERE/'check_case.py'),
        scope='Synthetic host negatives only; no DUT/reference/old CSV parse'))
    raise SystemExit(int(not result.wasSuccessful()))
