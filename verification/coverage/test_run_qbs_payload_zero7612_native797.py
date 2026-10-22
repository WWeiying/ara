import copy
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

import run_qbs_payload_zero7612_native797 as r


class LauncherTests(unittest.TestCase):
    def fixture(self):
        out=Path('/local/qbs')
        group='/user.slice/user-1000.slice/user@1000.service/app.slice/qbs-test.service'
        c=dict(output=str(out),identity=dict(executable='/sealed/dve',roles=dict(xvfb_run='/usr/bin/xvfb-run',launcher='/sealed/bin/dve')),expected_cgroup=group)
        live=[dict(pid=123,exe='/sealed/dve',cwd=str(out),cgroup='0::'+group+'\n')]
        witness=[dict(pid=123,executable='/sealed/dve',executable_verified=True,cwd=str(out),cgroup=live[0]['cgroup'],
                      worker_pid=333,launch_pid=222,launch_starttime=10,starttime=11,systemd_invocation='MODEL_ONLY')]
        e=dict(cwd=str(out),command=r.command(c,out),automatic_retry=False,timeout_seconds=900,
               worker_pid=333,worker_cgroup=live[0]['cgroup'],launch_pid=222,launch_starttime=10,systemd_invocation='MODEL_ONLY')
        return dict(returncode=0,timeout=False,actual_dve=live),c,live,witness,e

    def test_mature_terminal_positive_model_not_qualification(self): r.terminal_gate(*self.fixture())

    def test_terminal_exact_types(self):
        for key,values in [('returncode',[False,True,0.0,'0',1,None]),('timeout',[0,None,'false',True])]:
            for value in values:
                f=copy.deepcopy(self.fixture()); f[0][key]=value
                with self.assertRaises(ValueError): r.terminal_gate(*f)

    def test_pid_exe_cwd_cgroup_and_cardinality_rejected(self):
        for key,value in [('pid',False),('pid',0),('exe','/other'),('cwd','/tmp'),('cgroup','0::wrong')]:
            f=copy.deepcopy(self.fixture()); f[2][0][key]=value
            with self.assertRaises(ValueError): r.terminal_gate(*f)
        f=copy.deepcopy(self.fixture()); f[2].append(copy.deepcopy(f[2][0]))
        with self.assertRaises(ValueError): r.terminal_gate(*f)

    def test_witness_ancestry_starttime_worker_invocation(self):
        for key,value in [('pid',False),('executable_verified',1),('launch_pid',123),('launch_starttime',0),
                          ('starttime',9),('worker_pid',444),('systemd_invocation','other')]:
            f=copy.deepcopy(self.fixture()); f[3][0][key]=value
            with self.assertRaises(ValueError): r.terminal_gate(*f)

    def test_total900_no_retry_wrong_command(self):
        for key,value in [('timeout_seconds',901),('timeout_seconds',900.0),('automatic_retry',True),
                          ('command',['wrong']),('worker_cgroup','0::wrong')]:
            f=copy.deepcopy(self.fixture()); f[4][key]=value
            with self.assertRaises(ValueError): r.terminal_gate(*f)

    def test_exact_cgroup_not_substring(self):
        group=self.fixture()[1]['expected_cgroup']; r.cgroup_gate('0::'+group+'\n',group)
        for s in ('','0::'+group+'/child','0::'+group+'.extra','0::'+group+'\n1::other',None):
            with self.assertRaises(ValueError): r.cgroup_gate(s,group)

    def test_owning_service_required(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(ValueError):
            r.owning_gate(Path('/local/qbs'),self.fixture()[1])

    def test_no_parent_approval_never_load_or_start(self):
        for reviewed in (None,'','other'):
            with patch.object(r,'load_launch') as load,patch.object(r.subprocess,'Popen') as popen:
                with self.assertRaises(ValueError): r.run(Path('/unused'),'a'*64,reviewed)
                load.assert_not_called(); popen.assert_not_called()

    def test_atomic_launch_lock_and_evidence_prevent_retry(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)
            for name in ('launch-once.json','execution.json','terminal.json','first.el','native_before_0.tsv','bits_before_0.tsv'):
                p=out/name
                with p.open('x') as f: f.write('PRESERVE')
                with self.assertRaises(ValueError): r.fresh_gate(out)
                self.assertEqual(p.read_text(),'PRESERVE'); p.unlink()

    def test_service_command_only_model_no_execution(self):
        m=dict(host_tools=[dict(path='/usr/bin/systemd-run'),dict(path='/usr/bin/systemctl'),dict(path='/python')],
               unit='qbs-test.service',output='/local/qbs')
        cmd=r.service_command(Path('/unused'),'a'*64,m)
        self.assertIn('--property=RuntimeMaxSec=900',cmd)
        self.assertIn('--property=KillMode=control-group',cmd)
        self.assertIn('--parent-reviewed-seal',cmd)
        self.assertNotIn('VCS',str(cmd))

    def test_prepare_foreign_directory_never_checks_or_launches(self):
        with patch.object(r.core,'check') as check,patch.object(r.subprocess,'Popen') as popen:
            with self.assertRaises(ValueError): r.prepare(Path('/tmp/foreign'),Path('/unused'),'a'*64)
            check.assert_not_called(); popen.assert_not_called()

    def model_worker(self, reject=False):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td); terminal,c,live,witness,e=self.fixture()
            c['output']=str(out)
            for row in live: row['cwd']=str(out)
            for row in witness: row['cwd']=str(out)
            m=dict(native_config_sha256='b'*64)
            process=MagicMock(pid=222,returncode=0)
            process.poll.return_value=None
            p=MagicMock(); p.name='123'
            def member(name):
                result=MagicMock()
                result.resolve.return_value=Path('/sealed/dve') if name=='exe' else out
                return result
            p.__truediv__.side_effect=member
            def paths(value):
                if value=='/proc': return SimpleNamespace(iterdir=lambda:[p])
                if value=='/proc/self/cgroup': return SimpleNamespace(read_text=lambda:live[0]['cgroup'])
                return Path(value)
            observed={}
            def inspect(path,seal):
                import json
                observed['terminal']=json.loads((out/'terminal.json').read_bytes())
                self.assertEqual(observed['terminal']['returncode'],0)
                self.assertFalse(observed['terminal']['timeout'])
                return dict(known_toggle_qualification=False)
            with patch.object(r,'load_launch',return_value=(out,c,m)),patch.object(r,'owning_gate'), \
                 patch.object(r,'Path',side_effect=paths),patch.object(r,'live_gate',side_effect=ValueError('BAD_ANCESTRY') if reject else None,return_value=(live[0],witness[0])), \
                 patch.object(r.core.tools,'controlled_environment',return_value={}), \
                 patch.object(r.core.tools,'process_info',return_value=dict(starttime=10)), \
                 patch.object(r.subprocess,'Popen',return_value=process) as popen, \
                 patch.object(r.os,'killpg') as kill,patch.object(r,'inspect',side_effect=inspect), \
                 patch.object(r.time,'monotonic',side_effect=[100,105,110,115,120]), \
                 patch.dict(os.environ,INVOCATION_ID='MODEL_ONLY'):
                if reject:
                    with self.assertRaisesRegex(ValueError,'BAD_ANCESTRY'): r.run(Path('/unused'),'a'*64,'a'*64)
                    self.assertTrue((out/'worker-error.json').exists())
                    self.assertFalse((out/'live-ready').exists())
                    kill.assert_called_once_with(222,r.signal.SIGKILL)
                else:
                    result=r.run(Path('/unused'),'a'*64,'a'*64)
                    self.assertFalse(result['known_toggle_qualification'])
                    self.assertEqual(process.wait.call_args.kwargs['timeout'],870)
                    self.assertEqual(popen.call_args.kwargs['env']['QBS7612_SEAL'],'b'*64)
                    self.assertTrue(popen.call_args.kwargs['start_new_session'])
                    kill.assert_not_called()
                popen.assert_called_once()
                self.assertTrue((out/'launch-once.json').exists())
                self.assertTrue((out/'terminal.json').exists())

    def test_worker_model_total900s_and_no_qualification(self): self.model_worker()
    def test_worker_model_bad_ancestry_terminal_preserved_no_retry(self): self.model_worker(True)


if __name__=='__main__': unittest.main()
