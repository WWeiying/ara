"""Preserved runner coverage plus fail-closed completed-unit admission tests."""
import copy
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import replay_restart_units as r
import restart_dependency_gate as d
import test_restart_atomic as atomic


class Preserved(atomic.AtomicTests):
    def setUp(self):
        replacement = patch.object(atomic, 'r', r)
        replacement.start()
        self.addCleanup(replacement.stop)
        super().setUp()


class Dependencies(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.unit = 'ara-dependency-test.service'
        self.fields = dict(Id=self.unit, LoadState='not-found', ActiveState='inactive', SubState='dead',
                           MainPID='0', ControlPID='0', ControlGroup='')
        self.proc, self.cg = self.root / 'proc', self.root / 'cgroup'
        self.proc.mkdir()
        self.cg.mkdir()
        (self.cg / 'cgroup.controllers').write_text('cpu memory\n')

    def result(self, rc=0, stderr='', **changes):
        fields = dict(self.fields, **changes)
        return subprocess.CompletedProcess([], rc, '\n'.join(k + '=' + v for k, v in fields.items()) + '\n', stderr)

    def test_loaded_inactive(self):
        d.parse_unit(self.unit, self.result(LoadState='loaded'))

    def test_loaded_failed(self):
        d.parse_unit(self.unit, self.result(LoadState='loaded', ActiveState='failed', SubState='failed'))

    def test_collected_notfound_rc0(self):
        d.parse_unit(self.unit, self.result())

    def test_collected_complete_notfound_rc1(self):
        d.parse_unit(self.unit, self.result(rc=1))

    def test_exact_notfound_diagnostic(self):
        d.parse_unit(self.unit, self.result(rc=1, stderr=f'Unit {self.unit} could not be found.\n'))

    def test_active_rejected(self):
        with self.assertRaises(ValueError):
            d.parse_unit(self.unit, self.result(LoadState='loaded', ActiveState='active', SubState='running'))

    def test_unknown_load_rejected(self):
        with self.assertRaises(ValueError):
            d.parse_unit(self.unit, self.result(LoadState='error'))

    def test_unknown_returncode_rejected(self):
        with self.assertRaises(ValueError):
            d.parse_unit(self.unit, self.result(rc=4))

    def test_loaded_nonzero_rejected(self):
        with self.assertRaises(ValueError):
            d.parse_unit(self.unit, self.result(rc=1, LoadState='loaded'))

    def test_actual_bus_failure_rejected(self):
        result = subprocess.CompletedProcess([], 1, '', 'Failed to connect to bus: No medium found\n')
        with self.assertRaises(ValueError):
            d.parse_unit(self.unit, result)

    def test_complete_stdout_plus_bus_failure_rejected(self):
        with self.assertRaises(ValueError):
            d.parse_unit(self.unit, self.result(rc=1, stderr='Failed to connect to bus: No medium found'))

    def test_unknown_stderr_rejected(self):
        with self.assertRaises(ValueError):
            d.parse_unit(self.unit, self.result(stderr='Unexpected warning'))

    def test_missing_or_duplicate_or_wrong_id_rejected(self):
        for text in (self.result().stdout.replace('MainPID=0\n', ''), self.result().stdout + 'MainPID=0\n',
                     self.result(Id='ara-wrong.service').stdout, 'inactive\n'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                d.parse_unit(self.unit, subprocess.CompletedProcess([], 0, text, ''))

    def test_pid_and_controlgroup_rejected(self):
        for change in (dict(MainPID='2'), dict(ControlPID='3'), dict(ControlGroup='/user.slice/test')):
            with self.subTest(change=change), self.assertRaises(ValueError):
                d.parse_unit(self.unit, self.result(**change))

    def test_no_process_no_cgroup(self):
        d.absence([self.unit], self.proc, self.cg)

    def test_nonsimv_owned_process_rejected(self):
        proc = self.proc / '10'
        proc.mkdir()
        (proc / 'cgroup').write_text(f'0::/user.slice/app.slice/{self.unit}/child\n')
        with self.assertRaises(ValueError):
            d.absence([self.unit], self.proc, self.cg)

    def test_empty_unit_cgroup_rejected(self):
        (self.cg / 'app.slice' / self.unit).mkdir(parents=True)
        with self.assertRaises(ValueError):
            d.absence([self.unit], self.proc, self.cg)

    def test_missing_existing_process_cgroup_rejected(self):
        (self.proc / '10').mkdir()
        with self.assertRaises(ValueError):
            d.absence([self.unit], self.proc, self.cg)

    def test_cgroup_read_error_rejected(self):
        with patch.object(Path, 'read_text', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                d.absence([self.unit], self.proc, self.cg)

    def test_unknown_proc_cgroup_rejected(self):
        proc = self.proc / '10'
        proc.mkdir()
        (proc / 'cgroup').write_text('unknown')
        with self.assertRaises(ValueError):
            d.absence([self.unit], self.proc, self.cg)

    def test_sanitized_environment_recovers_only_trusted_bus(self):
        runtime = self.root / 'runtime'
        runtime.mkdir(mode=0o700)
        sock = socket.socket(socket.AF_UNIX)
        self.addCleanup(sock.close)
        sock.bind(str(runtime / 'bus'))
        with patch.dict(os.environ, {'PATH': '/usr/bin:/bin', 'HOME': str(self.root)}, clear=True):
            env = d.bus_environment(runtime)
        self.assertEqual(env['XDG_RUNTIME_DIR'], str(runtime))
        self.assertEqual(env['DBUS_SESSION_BUS_ADDRESS'], 'unix:path=' + str(runtime / 'bus'))
        self.assertNotIn('MAKEFLAGS', env)

    def test_missing_bus_rejected(self):
        with self.assertRaises(FileNotFoundError):
            d.bus_environment(self.root)

    def test_nonsocket_bus_rejected(self):
        (self.root / 'bus').write_text('not a socket')
        with self.assertRaises(ValueError):
            d.bus_environment(self.root)

    def test_query_uses_explicit_environment_and_bounded_timeout(self):
        env = dict(PATH='/usr/bin', XDG_RUNTIME_DIR='/trusted/runtime',
                   DBUS_SESSION_BUS_ADDRESS='unix:path=/trusted/runtime/bus')
        with patch.object(d, 'bus_environment', return_value=env), patch.object(d.subprocess, 'run', return_value=self.result()) as call:
            d.query_unit(self.unit)
        self.assertEqual(call.call_args.kwargs['env'], env)
        self.assertEqual(call.call_args.kwargs['timeout'], 5)

    def test_query_timeout_rejected(self):
        with patch.object(d, 'bus_environment', return_value={}), patch.object(d.subprocess, 'run',
                side_effect=subprocess.TimeoutExpired('systemctl', 5)):
            with self.assertRaises(subprocess.TimeoutExpired):
                d.query_unit(self.unit)

    def review(self):
        # Pinned actual terminal inputs; process and query observations below are
        # controlled fixtures, so these tests never admit or launch a DUT.
        return r.read(r.PREDECESSOR / 'parent_review.json')

    def test_full_terminal_membership_then_collected_admission(self):
        review = self.review()
        with patch.object(d, 'query_unit', return_value=dict(fixture='not-found')), \
             patch.object(d, 'absence', return_value=dict(owned_processes=[], unit_cgroups=[])):
            records = d.gates(review, review['plan_sha256'])
        self.assertEqual(len(records['gather_terminal']['results']), 75)
        self.assertIn('dependency_admission', records)

    def test_wrong_terminal_hash_rejected_before_query(self):
        review = self.review()
        review['evidence']['gather_terminal']['sha256'] = '0' * 64
        with patch.object(d, 'query_unit') as query:
            with self.assertRaises(ValueError):
                d.gates(review, review['plan_sha256'])
            query.assert_not_called()

    def test_wrong_membership_rejected_before_query(self):
        review = self.review()
        original = d.read
        def read(path):
            data = original(path)
            if Path(path) == d.GATHER / 'complete.json':
                data['results'][0]['name'] = 'wrong'
            return data
        with patch.object(d, 'read', read), patch.object(d, 'query_unit') as query:
            with self.assertRaises(ValueError):
                d.gates(review, review['plan_sha256'])
            query.assert_not_called()


if __name__ == '__main__':
    unittest.main()
