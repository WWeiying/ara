"""Host-only jobs8, pilot admission, capacity and plan-negative tests."""
import copy
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock,patch
import capacity8 as cap
import scheduler8 as schedule
import vcs_jobs8 as driver

class Gates(unittest.TestCase):
    def test_fixed_plan(self):
        p=dict(status='NF8_FULL192_JOBS8_PREFLIGHT_PASS_NOT_LAUNCHED',groups=list(range(48)),
          trials=list(range(192)),jobs=8,pilot=0,timeout_s=2400,case_outer_s=2520,service_outer_s=18000,
          image_sha256=driver.IMAGE_SHA,reserves=dict(nf7=2,parent38=4,gather=4,whole=6,own=8))
        driver.validate_plan(p)
        for key,value in [('groups',[0]),('trials',list(range(191))),('jobs',9),('pilot',1),
                          ('timeout_s',2401),('case_outer_s',2700),('service_outer_s',16800),
                          ('image_sha256','0'*64),('reserves',dict(nf7=0,parent38=4,own=8))]:
            bad=copy.deepcopy(p); bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): driver.validate_plan(bad)

    def test_pilot_failure_no_dispatch(self):
        seen=[]; callback=[]; abort=schedule.Abort()
        def fail(g,a): seen.append(g); return dict(status='FAIL')
        results=schedule.pilot_then_remaining(fail,abort,lambda r:callback.append(r))
        self.assertEqual(seen,[0]); self.assertEqual(callback,[])
        self.assertTrue(all(results[g]['status']=='CANCELLED_NOT_LAUNCHED' for g in range(1,48)))

    def test_pilot_evidence_failure_no_dispatch(self):
        seen=[]; abort=schedule.Abort()
        def one(g,a): seen.append(g); return dict(status='PASS')
        def refuse(r): raise ValueError('pilot input changed')
        results=schedule.pilot_then_remaining(one,abort,refuse)
        self.assertEqual(seen,[0]); self.assertIsNotNone(abort.reason)
        self.assertEqual(results[47]['status'],'CANCELLED_NOT_LAUNCHED')

    def test_pilot_then_eight_max(self):
        lock=threading.Lock(); live=0; peak=0; accepted=False; seen=[]
        def one(g,a):
            nonlocal live,peak
            with lock:
                if g: self.assertTrue(accepted)
                seen.append(g); live+=1; peak=max(peak,live)
            time.sleep(0.005)
            with lock: live-=1
            return dict(status='PASS')
        def accept(r):
            nonlocal accepted
            self.assertEqual(seen,[0]); accepted=True
        results=schedule.pilot_then_remaining(one,schedule.Abort(),accept)
        self.assertEqual(sorted(seen),list(range(48)))
        self.assertTrue(all(r['status']=='PASS' for r in results.values()))
        self.assertEqual(peak,8)

    def test_failure_cancels_queued(self):
        seen=[]; abort=schedule.Abort()
        def fail(g,a): seen.append(g); a.stop(dict(group=g)); return dict(status='FAIL')
        results=schedule.run_groups(list(range(48)),8,fail,abort)
        # Initial eight admissions may race the first failure; no later batch may start.
        self.assertTrue(seen and set(seen)<=set(range(8)))
        self.assertTrue(all(results[g]['status']=='CANCELLED_NOT_LAUNCHED' for g in range(8,48)))

    def test_accounting(self):
        parent='ara-parent38.service'
        units=dict(parent38=parent,gather='ara-gather.service',whole='ara-whole.service')
        def p(unit,n): return [dict(pid=i,cgroup='0::/app.slice/'+unit+'\n') for i in range(n)]
        baseline=p(cap.NF7_UNIT,2)+p(parent,4)
        self.assertEqual(cap.accounting(baseline,units,32*1024**3)['total_live_plus_reserved'],24)
        self.assertEqual(cap.accounting([],units,32*1024**3)['total_live_plus_reserved'],24)
        full=baseline+p(units['gather'],4)+p(units['whole'],6)
        self.assertEqual(cap.accounting(full,units,32*1024**3)['total_live_plus_reserved'],24)
        with self.assertRaises(ValueError): cap.accounting(baseline+p('other.service',1),units,32*1024**3)
        with self.assertRaises(ValueError): cap.accounting(baseline,units,32*1024**3-1)
        with self.assertRaises(ValueError): cap.accounting(baseline,dict(units,parent38=cap.NF7_UNIT),64*1024**3)
        with self.assertRaises(ValueError): cap.accounting(p(cap.NF7_UNIT,3)+p(parent,4),units,64*1024**3)
        with self.assertRaises(ValueError): cap.accounting(baseline+p(units['whole'],7),units,64*1024**3)
        with self.assertRaises(ValueError): cap.accounting(baseline,dict(parent38=parent),64*1024**3)

    def test_pam_and_inaccessible_simv(self):
        class Proc:
            name='123'
            def __init__(self,comm,argv): self.comm=comm; self.argv=argv
            def __truediv__(self,n):
                if n=='comm': return Mock(read_text=lambda:self.comm)
                if n=='cmdline': return Mock(read_bytes=lambda:self.argv)
                if n=='cgroup': return Mock(read_text=lambda:'0::/user.slice/init.scope\n')
                return Mock(resolve=Mock(side_effect=PermissionError('nondumpable')))
        self.assertIsNone(cap.snapshot_process(Proc('(sd-pam)',b'')))
        with self.assertRaises(PermissionError): cap.snapshot_process(Proc('simv',b'/image/simv\0'))
        with self.assertRaises(PermissionError): cap.snapshot_process(Proc('renamed',b'/image/simv\0+x\0'))

    def test_preflight_refuses_nonterminal(self):
        with patch.object(driver,'read',return_value=dict(status='RUNNING',trials=[])):
            with self.assertRaises(ValueError): driver.accepted_references()

    def test_no_implicit_launch(self):
        self.assertNotIn('--execute',driver.command(Path('/owned/unused')))
        cmd=driver.command(Path('/owned/unused'),0,True)
        self.assertEqual(cmd[cmd.index('--timeout')+1],'2400')
        self.assertEqual(cmd[cmd.index('--case')+1],'nf8_g00')
        self.assertIn('--execute',cmd)

if __name__=='__main__': unittest.main(verbosity=2)
