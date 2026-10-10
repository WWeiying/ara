import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import run_dtlb_ppn_swap1200 as m


class Runner(unittest.TestCase):
    def record(self,out=None):
        out=out or m.life.OUT/'synthetic-dtlb-not-launched'
        r = dict(schema=m.SCHEMA,case=m.CASE,output=str(out),timeout_s=1200,systemd_runtime_max_s=1260,
            automatic_retry=False,coverage_admitted=False,preflight=str(m.PRE),preflight_seal=m.PRE_SHA,
            baseline_seal=m.pre.BASE_SHA,command=m.command(out),pins={'/synthetic':'0'*64},
            service='ara-dtlb-test.service')
        return r

    def test_command_budget_source_immutable(self):
        r=self.record();self.assertEqual(m.validate_record(r),Path(r['output']))
        self.assertIn('+NO_FSDB',r['command']);self.assertEqual(r['command'][0],str(m.life.IMAGE))
        self.assertEqual(r['command'][-2:],['-do',str(m.PROBE)])
        q=m.life.read_bound(m.PRE,m.PRE_SHA)
        self.assertEqual(q['expected_vcs_budget_seconds'],300)
        self.assertEqual(q['counts']['matched_instructions'],191475)

    def test_changed_budget_or_command_rejected(self):
        for key,value in [('timeout_s',300),('timeout_s',True),('systemd_runtime_max_s',1200),
            ('automatic_retry',True),('baseline_seal','0'*64),('command',['other-simv']),('service','wrong.scope')]:
            r=self.record();r[key]=value
            with self.assertRaises(ValueError):m.validate_record(r)

    def test_real_source_proof(self):
        import collect_dtlb_ppn_swap1200 as c
        proof,pins=c.source_layout();m.life.check(pins)
        self.assertEqual((proof['update_width'],proof['tag_per_slot_width'],proof['content_per_slot_width']),
                         (189,61,128))

    def test_failed_pin_check_cannot_launch(self):
        with patch.object(m,'check',side_effect=ValueError('drift')),patch.object(m.subprocess,'Popen') as child:
            with self.assertRaises(ValueError):m.run(Path('/fake'),'0'*64)
            child.assert_not_called()

    def test_timeout1200_cleanup_no_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'run';r=self.record(out)
            child=Mock(pid=123,returncode=-15)
            child.wait.side_effect=[subprocess.TimeoutExpired(['fake'],1200),-15]
            with patch.object(m.life,'OUT',root),patch.object(m,'check',return_value=r),\
                 patch.object(m.life,'check'),patch.object(m.subprocess,'Popen',return_value=child) as launch,\
                 patch.object(m,'process_identity',return_value={'pid':123}),patch.object(m.os,'killpg'):
                r['pins'][str(m.life.IMAGE)]='0'*64
                with self.assertRaises(subprocess.TimeoutExpired):m.run(root/'record','0'*64)
                self.assertEqual(child.wait.call_args_list[0].kwargs,{'timeout':1200})
                self.assertEqual(launch.call_count,1)
            import json
            status=json.loads((out/'simulation-status.json').read_bytes())
            self.assertTrue(status['timeout']);self.assertFalse(status['automatic_retry'])
            self.assertEqual(status['status'],'SIMULATION_NOT_ADMITTED')

    def test_existing_output_no_relaunch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'run';out.mkdir();r=self.record(out)
            with patch.object(m.life,'OUT',root),patch.object(m,'check',return_value=r),\
                 patch.object(m.subprocess,'Popen') as child:
                with self.assertRaises(ValueError):m.run(root/'record','0'*64)
                child.assert_not_called()


if __name__=='__main__':unittest.main()
