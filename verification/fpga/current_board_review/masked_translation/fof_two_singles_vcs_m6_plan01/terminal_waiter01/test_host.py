"""Small offline Host tests; synthetic events only, never live trace reads."""
import copy
import csv
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
import waiter as w
fixture = w.c.load('fof_immutable_host_fixture', w.BASE/'test_host.py')

class Host(unittest.TestCase):
    def test_terminal_requires_both_actual_numeric_zeros(self):
        cases = w.c.scope()
        results = [dict(name=c['id'], status='PASS', returncode=0, elapsed_s=123., reason='') for c in cases]
        complete = dict(status=w.worker.PASS, aborted=False, pins_unchanged=True, retries=0, plan_sha256=w.PLAN_SHA, results=results)
        meta = dict(status='COMPLETE', status_counts={'PASS':2}, tests=[c['id'] for c in cases], jobs=2, timeout_s=1800)
        monitors = {c['id']:dict(returncode=0,elapsed_s=123.,timed_out=False,failure_seen=False,abort_set=False,architectural_acceptance=False) for c in cases}
        children = {r['name']:dict(r,architectural_acceptance=False) for r in results}
        args = [complete,meta,results,monitors,children,cases]
        self.assertEqual(w.terminal_gate(*args),results)
        for n in monitors:
            for key,value in [('returncode',None),('returncode',False),('returncode',255),('abort_set',True),('timed_out',True)]:
                changed=copy.deepcopy(args);changed[3][n][key]=value
                with self.subTest(name=n,key=key,value=value),self.assertRaises(ValueError):w.terminal_gate(*changed)
        for key,value in [('status','NOT_PASS'),('aborted',True),('pins_unchanged',False)]:
            changed=copy.deepcopy(args);changed[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):w.terminal_gate(*changed)
        changed=copy.deepcopy(args);changed[1]['status']='INTERRUPTED'
        with self.assertRaises(ValueError):w.terminal_gate(*changed)

    def test_independent_full_two_shapes_and_defined_corruptions(self):
        for sew in (8,64):
            spec=w.c.specification(sew);rows,labels=fixture.synthetic(spec)
            check=w.Numerical(spec);saved={}
            addresses=[spec['symbols']['fx_out']+(sew//8)*i for i in (1,9,129)]
            positions={labels[f'p1_read_{a:x}'] for a in addresses}
            for i,row in enumerate(rows):
                if i in positions:saved[i]=copy.deepcopy(check)
                check.row(row)
            result=check.finish()
            self.assertEqual(result['checks'],5477 if sew==8 else 5481)
            self.assertEqual(result['full_page_word_reads'],5120)
            self.assertEqual(result['defined_output_reads'],[130,126 if sew==8 else 130])
            for at,model in saved.items():
                with self.subTest(sew=sew,at=at),self.assertRaises(ValueError):
                    model.row(dict(rows[at],rd_wdata='0'))
            final=check.values(1)
            if sew==8:
                for i in range(5,9):self.assertNotIn(spec['symbols']['fx_out']+i,[a for a,_,_ in final])
            else:
                self.assertEqual([v for a,width,v in final if spec['symbols']['fx_out']<=a<spec['symbols']['fx_out']+1040],[0x5b]*130)

    def test_combined_generic_single_stream(self):
        class Counter:
            rows=0
            def row(self,_):self.rows+=1
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.csv'
            with path.open('w') as stream:
                writer=csv.writer(stream);writer.writerow(w.scalar_decoder.FIELDS)
                writer.writerow([1,'retire',0,0,0,'80000000','13',0,'0','0','0','0','0',0])
            counter=Counter();wrapped=w.CombinedPath(path,counter)
            result=w.validate_trace(wrapped)
            self.assertEqual(result['retire_count'],1);self.assertEqual(counter.rows,1)
            self.assertEqual(wrapped.digest.hexdigest(),hashlib.sha256(path.read_bytes()).hexdigest())

    def test_terminal_inotify_rename_and_already_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'complete.json'
            def publish():
                temporary=path.with_suffix('.tmp');temporary.write_text('{}');temporary.rename(path)
            timer=threading.Timer(.05,publish);timer.start()
            try:w.wait_terminal(path,2);w.wait_terminal(path,2)
            finally:timer.join()

if __name__=='__main__':unittest.main(verbosity=2)
