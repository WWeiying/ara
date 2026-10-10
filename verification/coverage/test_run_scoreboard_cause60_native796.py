"""Offline mature worker/authorization/service contract checks; never launches EDA."""
import copy
import inspect
import json
import unittest
from unittest.mock import patch

import run_scoreboard_cause60_native796 as m


class Launcher(unittest.TestCase):
    def test_explicit_exact_parent_seal_only(self):
        m.approve('a'*64,'a'*64)
        for seal,parent in [(None,None),('a'*64,None),('a'*64,'b'*64),('z'*64,'z'*64)]:
            with self.subTest(seal=seal),self.assertRaises(ValueError):m.approve(seal,parent)

    def test_single900_service_not_nested_or_retry(self):
        manifest=dict(manifest_path=str(m.LAUNCH/'launch-manifest.json'))
        command=m.service_command(manifest,'a'*64)
        self.assertIn('--property=RuntimeMaxSec=900',command)
        self.assertIn('--property=KillMode=control-group',command)
        self.assertIn('--property=Restart=no',command)
        self.assertIn('--property=Type=exec',command)
        self.assertNotIn('960',' '.join(command));self.assertNotIn('nohup',' '.join(command))
        self.assertEqual(command[-2:],['--parent-reviewed-seal','a'*64])

    def test_prepare_and_compiled_worker_never_start_process(self):
        with patch.object(m.subprocess,'Popen',side_effect=AssertionError('EDA start prohibited')):
            fn=m.worker(m.LAUNCH/'launch-manifest.json','STATIC_ONLY')
        self.assertTrue(callable(fn))
        code=inspect.getsource(m.prepare)
        self.assertNotIn('Popen(',code);self.assertNotIn('subprocess.run(',code)

    def test_exact_cgroup_and_live_ancestry_policy(self):
        m.mature.cgroup_gate('0::'+m.CGROUP+'\n',m.CGROUP)
        for text in ('0::/wrong\n','0::'+m.CGROUP+'/child\n','0::'+m.CGROUP+'\n0::/other\n'):
            with self.subTest(text=text),self.assertRaises(ValueError):m.mature.cgroup_gate(text,m.CGROUP)

    def test_terminal_bool_float_timeout_missing_actual_process_rejected(self):
        c=dict(identity=dict(executable='/sealed/dve.exe'),expected_cgroup=m.CGROUP)
        p=dict(pid=20,exe='/sealed/dve.exe',cwd=str(m.OUT),cgroup='0::'+m.CGROUP+'\n')
        w=dict(pid=20,executable=p['exe'],cwd=p['cwd'],cgroup=p['cgroup'],executable_verified=True,
               launch_pid=10,worker_pid=5,starttime=200,launch_starttime=100,systemd_invocation='exact')
        e=dict(automatic_retry=False,timeout_seconds=900,systemd_invocation='exact')
        t=dict(returncode=0,timeout=False,actual_dve=[p])
        m.terminal_gate(t,c,[p],[w],e)
        for key,value in [('returncode',False),('returncode',0.0),('returncode','0'),
                          ('timeout',0),('timeout',True),('actual_dve',[])]:
            bad=copy.deepcopy(t);bad[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):m.terminal_gate(bad,c,[p],[w],e)

    def test_one_shot_lock_and_no_capture_reuse(self):
        code=inspect.getsource(m.run)
        self.assertIn("'launch-once.json'",code)
        self.assertIn("OUT.glob('objects_*.tsv')",code)
        self.assertIn("OUT.glob('bits_*.tsv')",code)
        self.assertIn('owning_gate(OUT,c)',code)


if __name__=='__main__':unittest.main()
