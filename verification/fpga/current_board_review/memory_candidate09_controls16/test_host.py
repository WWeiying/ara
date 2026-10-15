"""Focused wrapper Host: no simulation, source build, or baseline replay."""
import tempfile
from pathlib import Path
import unittest
import worker as w


class Contract(unittest.TestCase):
    def test_exact_accepted_M8_16(self):
        cases,pins=w.scope()
        self.assertEqual(len(cases),16)
        self.assertTrue(all(c['kind']=='control' and c['timeout_s']==180 for c in cases))
        self.assertTrue(all(str(w.OLD/'regression19/tests') in c['baseline_csv'] for c in cases))
        w.m7.base.verify_pins(pins)

    def test_actual_M9_frozen_configuration(self):
        ledger,repo,(parent,options,testcase,_)=w.image_context()
        self.assertEqual(ledger['configuration_sha256'],w.m7.CONFIGURATION_SHA)
        self.assertIn('candidate09',ledger['simv'])
        opts=options(repo,Path('/tmp/no-execution'),'default',1,1,True,False,True,Path(ledger['simv']),True,None)
        self.assertTrue(opts.skip_build)
        self.assertEqual(opts.jobs,1)

    def test_numeric_exit_strict(self):
        good=dict(returncode=0,elapsed_s=1,timed_out=False,failure_seen=False)
        w.numeric(good)
        for key,value in [('returncode',False),('returncode',17),('timed_out',True),
                          ('failure_seen',True),('elapsed_s',181)]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                w.numeric(dict(good,**{key:value}))

    def test_full_cycle_comparison_and_noncycle_veto(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a.csv',Path(d)/'b.csv'
            a.write_text('cycle,event,order\n1,retire,0\n2,retire,1\n')
            b.write_text(a.read_text())
            self.assertEqual(w.m7.compare_cycles(a,b,Path(d)/'eq.csv')['cycle_changed_rows'],0)
            b.write_text('cycle,event,order\n1,retire,0\n3,retire,1\n')
            result=w.m7.compare_cycles(a,b,Path(d)/'delta.csv')
            self.assertEqual((result['rows'],result['cycle_changed_rows'],result['last_cycle_delta']),(2,1,1))
            b.write_text('cycle,event,order\n1,retire,0\n3,retire,9\n')
            with self.assertRaisesRegex(ValueError,'Noncycle'):
                w.m7.compare_cycles(a,b,Path(d)/'bad.csv')

    def test_resource_cap_not_bypassed(self):
        with self.assertRaises(ValueError):
            w.m7.resource_math([{'argv':['simv']}] * 24,64*1024**3,Path('/tmp/new'),1,0)
        with self.assertRaises(ValueError):
            w.m7.resource_math([],31*1024**3,Path('/tmp/new'),1,0)


if __name__=='__main__':unittest.main()
