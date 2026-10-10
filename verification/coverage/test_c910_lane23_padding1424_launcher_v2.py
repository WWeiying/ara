"""Authorization, systemd ownership, actual-child and terminal negative tests; no EDA."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import c910_lane23_padding1424_launcher_v2 as m


class Launcher1424(unittest.TestCase):
    def test_precheck_errors_always_record_nonzero_without_native(self):
        for stage in ('approval', 'check', 'environment'):
            with tempfile.TemporaryDirectory() as d:
                out = Path(d)
                c, _, _ = self.model(out)
                with patch.object(m, 'check', side_effect=ValueError('check failed') if stage == 'check' else None,
                                  return_value=c), patch.dict(os.environ, C1424_CONFIG_SEAL='wrong'), \
                     patch.object(m.subprocess, 'Popen') as popen:
                    with self.assertRaises(ValueError):
                        m.worker(out, 'a' * 64, None if stage == 'approval' else 'a' * 64)
                    popen.assert_not_called()
                error = json.loads((out / 'worker-error.json').read_text())
                terminal = json.loads((out / 'terminal.json').read_text())
                self.assertEqual(error['phase'], 'precheck')
                self.assertEqual(error['returncode'], 1)
                self.assertFalse(error['EDA_started'])
                self.assertEqual(terminal['returncode'], 1)
                self.assertFalse(terminal['EDA_started'])
                self.assertFalse((out / 'execution.json').exists())

    def model(self, out):
        group = '0::/user.slice/user-1000.slice/user@1000.service/app.slice/c9101424-local-host.service\n'
        c = dict(output=str(out), identity=dict(executable='/sealed/dve.exe',
            roles=dict(launcher='/sealed/dve', xvfb_run='/usr/bin/xvfb-run')),
            launch_contract=dict(unit='c9101424-local-host', uid=1000, pythonpath='/host/imports',
                host_tools=[dict(path=p) for p in ('/usr/bin/systemd-run', '/usr/bin/systemctl', '/usr/bin/python3')]))
        e = dict(command=m.core.ptw.command(c, out), cwd=str(out), config_seal='a' * 64,
            timeout_seconds=900, service_unit=c['launch_contract']['unit'], worker_pid=1111,
            worker_cgroup=group, launch_pid=2222, launch_starttime=100)
        row = dict(pid=3333, exe='/sealed/dve.exe', cwd=str(out), cgroup=group,
            process_identity=dict(executable_verified=True, pid=3333, executable='/sealed/dve.exe',
                starttime=101, launch_pid=2222, launch_starttime=100))
        return c, e, row

    def test_review_mismatch_rejected_before_any_process(self):
        with patch.object(m.subprocess, 'run') as run, patch.object(m.subprocess, 'Popen') as popen:
            for reviewed in (None, '', 'b' * 64):
                with self.assertRaises(ValueError):
                    m.launch(Path('/unused'), 'a' * 64, reviewed)
            run.assert_not_called()
            popen.assert_not_called()

    def test_prepare_existing_directory_and_tool_identity_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            with patch.object(m.subprocess, 'run') as run, patch.object(m.subprocess, 'Popen') as popen:
                with self.assertRaises(ValueError):
                    m.prepare(out)
                run.assert_not_called()
                popen.assert_not_called()
            c, _, _ = self.model(out)
            with patch.object(m.core, 'check', return_value=c), \
                 patch.object(m, 'contract', return_value=dict(c['launch_contract'], timeout_seconds=901)):
                with self.assertRaises(ValueError):
                    m.check(out, 'a' * 64)

    def test_systemd_command_owns_worker_directly_and_has900_no_retry(self):
        c, _, _ = self.model(Path('/host/output'))
        cmd = m.service_command(c, Path('/host/output'), 'a' * 64)
        self.assertIn('--property=KillMode=control-group', cmd)
        self.assertIn('--property=RuntimeMaxSec=900', cmd)
        self.assertIn('--property=Type=exec', cmd)
        self.assertIn('--setenv=C1424_CONFIG_SEAL=' + 'a' * 64, cmd)
        self.assertEqual(cmd[cmd.index('/usr/bin/python3') + 1:][:3], ['-B', str(m.SCRIPT), 'worker'])
        self.assertNotIn('sh', cmd)
        self.assertNotIn('--scope', cmd)
        self.assertNotIn('--collect', cmd)
        self.assertIn('--property=Restart=no', cmd)
        self.assertIn('--property=StandardOutput=append:/host/output/service-stdout.log', cmd)
        self.assertIn('--property=StandardError=append:/host/output/service-stderr.log', cmd)

    def test_foreign_service_and_child_identity_rejected(self):
        c, e, row = self.model(Path('/host/output'))
        m.live_gate(row, c, e)
        for key, value in [('pid', True), ('exe', '/foreign/dve.exe'), ('cwd', '/other'),
                           ('cgroup', row['cgroup'].replace('local-host', 'local-foreign'))]:
            bad = dict(row, **{key: value})
            with self.assertRaises(ValueError):
                m.live_gate(bad, c, e)
        for key, value in [('executable_verified', False), ('launch_pid', 999),
                           ('launch_starttime', 99), ('starttime', 0)]:
            bad = copy.deepcopy(row)
            bad['process_identity'][key] = value
            with self.assertRaises(ValueError):
                m.live_gate(bad, c, e)
        for group in ('0::/direct-shell\n', row['cgroup'].replace('user@1000', 'user@999')):
            with self.assertRaises(ValueError):
                m.cgroup_gate(group, c['launch_contract'])

    def test_retry_and_direct_worker_never_start_native(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            c, _, _ = self.model(out)
            (out / 'service-request.json').write_text('{}\n')
            with patch.object(m, 'check', return_value=c), patch.object(m.subprocess, 'run') as run:
                with self.assertRaises(ValueError):
                    m.launch(out, 'a' * 64, 'a' * 64)
                run.assert_not_called()
            with patch.object(m, 'check', return_value=c), patch.object(m, 'proc_cgroup', return_value='0::/shell\n'), \
                 patch.dict(os.environ, C1424_CONFIG_SEAL='a' * 64), patch.object(m.subprocess, 'Popen') as popen:
                with self.assertRaises(ValueError):
                    m.worker(out, 'a' * 64, 'a' * 64)
                popen.assert_not_called()

    def test_strict_terminal_nonzero_boolean_timeout_foreign_command(self):
        out = Path('/host/output')
        c, e, row = self.model(out)
        live = [row]
        terminal = dict(returncode=0, timeout=False, actual_dve=live)
        m.core.ptw.terminal_gate(c, 'a' * 64, out, terminal, live, e)
        for changes in (dict(returncode=False), dict(returncode=1), dict(timeout=True), dict(actual_dve=[])):
            with self.assertRaises(ValueError):
                m.core.ptw.terminal_gate(c, 'a' * 64, out, dict(terminal, **changes), live, e)
        bad = copy.deepcopy(e)
        bad['command'][0] = '/foreign/xvfb-run'
        with self.assertRaises(ValueError):
            m.core.ptw.terminal_gate(c, 'a' * 64, out, terminal, live, bad)

    def test_worker_host_mock_waits_and_records_environment_identity_terminal(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            c, e, row = self.model(out)
            seal = 'a' * 64
            request = dict(command=m.service_command(c, out, seal), reviewed_seal=seal)
            (out / 'service-request.json').write_text(json.dumps(request))
            (out / 'service-launch-receipt.json').write_text('{}\n')
            proc = Mock(pid=2222, returncode=0)
            proc.wait.return_value = 0
            with patch.object(m, 'check', return_value=c), \
                 patch.object(m, 'proc_cgroup', return_value=row['cgroup']), \
                 patch.object(m.tools, 'controlled_environment', return_value={}), \
                 patch.object(m.tools, 'process_info', return_value=dict(starttime=100)), \
                 patch.object(m, 'observe', return_value=[row]), \
                 patch.object(m, 'verify', return_value=dict(status='HOST_MOCK_ONLY')) as verify, \
                 patch.dict(os.environ, C1424_CONFIG_SEAL=seal), \
                 patch.object(m.subprocess, 'Popen', return_value=proc) as popen:
                result = m.worker(out, seal, seal)
            self.assertEqual(result['status'], 'HOST_MOCK_ONLY')
            self.assertEqual(popen.call_args.kwargs['env']['C1424_CONFIG_SEAL'], seal)
            self.assertEqual(popen.call_args.kwargs['env']['DVE_COVERAGE_OUTPUT'], str(out))
            self.assertTrue(proc.wait.called)
            self.assertEqual(json.loads((out / 'terminal.json').read_bytes())['returncode'], 0)
            self.assertEqual(json.loads((out / 'live-identity.json').read_bytes()), [row])
            self.assertEqual(json.loads((out / 'execution.json').read_bytes())['worker_cgroup'], row['cgroup'])
            verify.assert_called_once_with(out, seal)

    def test_verify_writes_capture_result_only_after_both_gate_sets(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            c, e, row = self.model(out)
            seal = 'a' * 64
            cmd = m.service_command(c, out, seal)
            artifacts = dict(**{'execution.json': e, 'live-identity.json': [row],
                'service-request.json': dict(config_seal=seal, reviewed_seal=seal, command=cmd,
                    unit=c['launch_contract']['unit'], uid=1000, timeout_seconds=900),
                'service-launch-receipt.json': dict(returncode=0, command=cmd)})
            for name, value in artifacts.items():
                (out / name).write_text(json.dumps(value))
            for name in ('worker.log', 'launcher.log', 'service-stdout.log', 'service-stderr.log'):
                (out / name).write_text('HOST MOCK ONLY\n')
            with patch.object(m, 'check', return_value=c), \
                 patch.object(m.core, 'verify', side_effect=ValueError('Missing native stages')):
                with self.assertRaises(ValueError):
                    m.verify(out, seal)
                self.assertFalse((out / 'capture-result.json').exists())
            with patch.object(m, 'check', return_value=c), \
                 patch.object(m.core, 'verify', return_value=dict(status='HOST_MOCK_NOT_NATIVE', pins={})):
                result = m.verify(out, seal)
            self.assertEqual(json.loads((out / 'capture-result.json').read_bytes()), result)
            self.assertEqual(result['status'], 'HOST_MOCK_NOT_NATIVE')

    def test_failed_worker_preserves_actual_terminal_and_never_qualifies(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            c, _, row = self.model(out)
            seal = 'a' * 64
            (out / 'service-request.json').write_text(json.dumps(
                dict(command=m.service_command(c, out, seal), reviewed_seal=seal)))
            proc = Mock(pid=2222, returncode=17)
            proc.poll.return_value = 17
            with patch.object(m, 'check', return_value=c), \
                 patch.object(m, 'proc_cgroup', return_value=row['cgroup']), \
                 patch.object(m.tools, 'controlled_environment', return_value={}), \
                 patch.object(m.tools, 'process_info', return_value=dict(starttime=100)), \
                 patch.object(m, 'observe', return_value=[]), \
                 patch.dict(os.environ, C1424_CONFIG_SEAL=seal), \
                 patch.object(m.subprocess, 'Popen', return_value=proc):
                with self.assertRaises(ValueError):
                    m.worker(out, seal, seal)
            self.assertEqual(json.loads((out / 'terminal.json').read_bytes())['returncode'], 17)
            with patch.object(m, 'check', return_value=c):
                with self.assertRaisesRegex(ValueError, 'Recorded worker failure'):
                    m.verify(out, seal)
            self.assertFalse((out / 'capture-result.json').exists())


if __name__ == '__main__':
    unittest.main()
