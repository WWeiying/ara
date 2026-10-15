"""Host-only negative admission and stop-first-failure queue checks."""
import copy
import unittest
import vcs_adapter as a

class Admission(unittest.TestCase):
    def test_fixed_plan(self):
        plan=dict(status='NF8_CANDIDATE04_PREFLIGHT_PASS_NOT_LAUNCHED',trials=a.TRIALS,
                  jobs=2,timeout_s=1800,case_outer_s=1950,service_outer_s=5400,image_sha256=a.IMAGE_SHA)
        a.validate_plan(plan)
        for key,value in [('status','PASS'),('trials',[19]),('jobs',3),('timeout_s',1801),
                          ('case_outer_s',2000),('service_outer_s',1800),('image_sha256','0'*64)]:
            bad=copy.deepcopy(plan); bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): a.validate_plan(bad)

    def test_cancel_queue(self):
        abort=a.scheduler.Abort(); called=[]
        def fail(t,control):
            called.append(t); control.stop(dict(host_failure=t)); return dict(status='FAIL')
        result=a.scheduler.run_groups(a.TRIALS,1,fail,abort)
        self.assertEqual(called,[19])
        self.assertEqual([result[t]['status'] for t in a.TRIALS],['FAIL']+['CANCELLED_NOT_LAUNCHED']*3)

    def test_no_implicit_execute(self):
        self.assertNotIn('--execute',a.command(a.HERE/'host_unused'))
        cmd=a.command(a.HERE/'host_unused',19,True)
        self.assertIn('--execute',cmd)
        self.assertEqual(cmd[cmd.index('--timeout')+1],'1800')
        self.assertEqual(cmd[cmd.index('--case')+1],'nf8_trial19')

if __name__=='__main__': unittest.main(verbosity=2)
