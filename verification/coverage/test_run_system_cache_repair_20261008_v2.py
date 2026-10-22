"""Offline prerequisite tests: no EDA, subprocess execution or old-result writes."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_system_cache_repair_20261008_v2 as r


MISSING = dict(LoadState='not-found', ActiveState='inactive', MainPID='0', ExecMainStatus='0')


class Gate(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.acc, self.image_dir = self.root / 'acceptance06', self.root / 'image04'
        self.image = self.image_dir / 'sim/simv'
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b'image fixture, not executable')
        self.rtl = self.root / 'rtl.sv'
        self.rtl.write_text('module frozen; endmodule\n')
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'input.elf').write_bytes(b'original ELF')
        self.patch(r, 'IMAGE_DIR', self.image_dir)
        self.patch(r.accepted.legacy, 'source', return_value=self.source)
        self.patch(r.accepted.legacy, 'simulation_command', side_effect=lambda image, d, n:
                   [str(image), '+PRELOAD=' + str(d / 'input.elf')])
        self.completed = self.patch(r.accepted.prior, 'completed_logs',
                                   return_value=dict(status='PASS', last_cycle=10, finish_fs=20000000))
        self.gone = self.patch(r, 'ensure_simulator_gone')
        for filename, value in [('build-status.json', {'status': 'PASS'}),
                                ('build-image.json', r.base.pins([self.image])),
                                ('build-source-pins.json', r.base.pins([self.rtl]))]:
            r.base.save(self.image_dir / filename, value)
        self.acc.mkdir()
        self.pins = r.base.pins([self.rtl, self.image, Path(r.accepted.__file__),
                                Path(r.accepted.prior.__file__), Path(r.accepted.legacy.__file__)])
        self.runner_sha = r.base.sha256(Path(r.accepted.__file__))
        self.build = self.patch(r.accepted, 'build_evidence',
                               return_value=(r.base.pins([self.rtl, self.image]), {}))
        r.base.save(self.acc / 'source-pins.json', self.pins)
        self.state = dict(status='PASS', total=23, image=str(self.image), fresh_runs_only=True, cases={})
        for name in r.accepted.prior.EXPECTED_SCOPE:
            case = self.acc / 'results' / name
            case.mkdir(parents=True)
            (case / 'input.elf').write_bytes((self.source / 'input.elf').read_bytes())
            for filename in r.accepted.prior.RAW_FILES:
                (case / filename).write_bytes(b'raw evidence\n')
            origin = case
            command = r.accepted.legacy.simulation_command(self.image, origin, name)
            launch = dict(pid=123, image=str(self.image), started_unix=1,
                image_sha256=r.base.sha256(self.image), elf_sha256=r.base.sha256(case / 'input.elf'),
                command=command)
            r.base.save(origin / 'started.json', launch)
            r.base.save(origin / 'command.json', dict(command=command, cwd=str(origin), timeout_s=1800))
            exit_path = case / 'simulation-exit.json'
            r.base.save(exit_path, dict(launch, returncode=0, timeout=False, finished_unix=2,
                                       exit_observed_by='owning worker Popen.wait'))
            receipt = dict(status='PASS', directory=str(case), last_cycle=10,
                           evidence=dict(checks=12, failures=0), simulation_launched=True,
                           reused_completed_same_image=False, simulator_process_exit_verified=True,
                           process_exit_receipt=str(exit_path), process_exit_receipt_sha256=r.base.sha256(exit_path))
            self.state['cases'][name] = receipt
            r.base.save(case / 'audit.json', receipt)
        self.seal_status()
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('no EDA')))
        self.stack.enter_context(patch('subprocess.run', side_effect=AssertionError('no subprocess')))

    def patch(self, obj, name, *args, **kwargs):
        return self.stack.enter_context(patch.object(obj, name, *args, **kwargs))

    def seal_status(self):
        r.base.save(self.acc / 'status.json', self.state)

    def gate(self, service=None):
        return r.acceptance_gate(self.acc, self.image_dir, service or MISSING, self.runner_sha)

    def test_collected_success_unit_uses_all_23_evidence(self):
        result = self.gate()
        self.assertEqual(result['count'], 23)
        self.assertEqual(len(result['cases']), 23)
        self.assertTrue(result['service_collected'])
        self.assertTrue(result['independent_process_exit_receipt'])
        self.assertEqual(self.completed.call_count, 23)
        self.assertEqual(self.gone.call_count, 23)

    def test_loaded_terminal_success_supported(self):
        self.assertFalse(self.gate(dict(MISSING, LoadState='loaded'))['service_collected'])

    def test_service_running_or_failed_rejected(self):
        for service in (dict(MISSING, LoadState='loaded', ActiveState='active', MainPID='1'),
                        dict(MISSING, ActiveState='failed'),
                        dict(MISSING, LoadState='loaded', ExecMainStatus='1'),
                        dict(MISSING, MainPID='1'), dict(MISSING, LoadState='error')):
            with self.subTest(service=service), self.assertRaises(RuntimeError):
                self.gate(service)

    def test_missing_unit_default_exit_status_is_not_evidence(self):
        self.state['status'] = 'RUNNING'
        self.seal_status()
        with self.assertRaisesRegex(RuntimeError, 'must pass'):
            self.gate()

    def test_one_nonpass_blocks(self):
        for value in ('FAIL', 'TIMEOUT', 'RUNNING', 'QUEUED'):
            with self.subTest(value=value):
                self.state['cases']['axpy']['status'] = value
                self.seal_status()
                with self.assertRaisesRegex(RuntimeError, 'recorded PASS'):
                    self.gate()

    def test_missing_case_blocks(self):
        del self.state['cases']['axpy']
        self.seal_status()
        with self.assertRaisesRegex(RuntimeError, 'must pass'):
            self.gate()

    def test_missing_status_blocks(self):
        (self.acc / 'status.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'must pass'):
            self.gate()

    def test_changed_source_manifest_blocks(self):
        (self.acc / 'source-pins.json').write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'source differs'):
            self.gate()

    def test_changed_source_file_blocks(self):
        self.rtl.write_text('changed RTL')
        with self.assertRaises(Exception):
            self.gate()

    def test_changed_image_blocks(self):
        self.image.write_bytes(b'other image')
        with self.assertRaises(Exception):
            self.gate()

    def test_wrong_build_manifest_blocks(self):
        self.build.return_value = ({str(self.rtl): 'wrong'}, {})
        with self.assertRaisesRegex(RuntimeError, 'source differs'):
            self.gate()

    def test_still_live_simulator_blocks(self):
        self.gone.side_effect = RuntimeError('recorded simulator is still running')
        with self.assertRaisesRegex(RuntimeError, 'still running'):
            self.gate()

    def test_incomplete_finish_blocks(self):
        self.completed.side_effect = RuntimeError('missing normal simulator finish/report')
        with self.assertRaisesRegex(RuntimeError, 'finish/report'):
            self.gate()

    def test_wrong_completion_cycle_blocks(self):
        self.completed.return_value = dict(last_cycle=11)
        with self.assertRaisesRegex(RuntimeError, 'cycle differs'):
            self.gate()

    def test_changed_elf_blocks(self):
        (self.acc / 'results/axpy/input.elf').write_bytes(b'other ELF')
        with self.assertRaisesRegex(RuntimeError, 'ELF differs'):
            self.gate()

    def test_bad_command_blocks(self):
        p = self.acc / 'results/axpy/command.json'
        data = r.base.read(p)
        data['timeout_s'] = 1
        r.base.save(p, data)
        with self.assertRaisesRegex(RuntimeError, 'launch contract'):
            self.gate()

    def test_default_does_not_launch(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(r.main([]), 0)
        self.assertIn('PREPARED_ONLY', out.getvalue())

    def test_build_not_pass_blocks(self):
        self.build.side_effect = RuntimeError('Completed fresh source-checked build required')
        with self.assertRaisesRegex(RuntimeError, 'source-checked build'):
            self.gate()

    def test_missing_exit_receipt_blocks(self):
        (self.acc / 'results/axpy/simulation-exit.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.gate()

    def test_nonzero_exit_or_timeout_blocks_even_with_pass_audit(self):
        path = self.acc / 'results/axpy/simulation-exit.json'
        original = r.base.read(path)
        for changes in (dict(returncode=1), dict(timeout=True), dict(image='wrong'), dict(finished_unix=0)):
            with self.subTest(changes=changes):
                r.base.save(path, dict(original, **changes))
                self.state['cases']['axpy']['process_exit_receipt_sha256'] = r.base.sha256(path)
                r.base.save(path.parent / 'audit.json', self.state['cases']['axpy'])
                self.seal_status()
                with self.assertRaisesRegex(RuntimeError, 'zero-exit receipt'):
                    self.gate()

    def test_old_reused_receipts_not_allowed(self):
        self.state['cases']['axpy']['simulation_launched'] = False
        r.base.save(self.acc / 'results/axpy/audit.json', self.state['cases']['axpy'])
        self.seal_status()
        with self.assertRaisesRegex(RuntimeError, 'fresh completed'):
            self.gate()

    def test_runner_hash_required(self):
        with self.assertRaisesRegex(RuntimeError, 'runner differs'):
            r.acceptance_gate(self.acc, self.image_dir, MISSING, 'wrong')


class ProcessAndFinish(unittest.TestCase):
    def test_future_acceptance_waits_and_success_collection_is_supported(self):
        running = dict(MISSING, LoadState='loaded', ActiveState='active', MainPID='123')
        for status in ({}, {'status': 'WAITING_BUILD'}, {'status': 'RUNNING'}, {'status': 'PASS'}):
            self.assertFalse(r.acceptance_ready(status, running))
        self.assertTrue(r.acceptance_ready({'status': 'PASS'}, MISSING))
        for status in ({}, {'status': 'RUNNING'}, {'status': 'STOPPED'}):
            with self.assertRaises(RuntimeError):
                r.acceptance_ready(status, MISSING)

    def test_dead_pid_allowed(self):
        with patch.object(Path, 'read_bytes', side_effect=FileNotFoundError):
            r.ensure_simulator_gone(dict(pid=123, image='/x/simv'))

    def test_live_original_pid_denied(self):
        with patch.object(Path, 'read_bytes', return_value=b'/x/simv\0-l\0run.vcs.log\0'):
            with self.assertRaisesRegex(RuntimeError, 'still running'):
                r.ensure_simulator_gone(dict(pid=123, image='/x/simv'))

    def test_recycled_pid_allowed(self):
        with patch.object(Path, 'read_bytes', return_value=b'/usr/bin/unrelated\0'):
            r.ensure_simulator_gone(dict(pid=123, image='/x/simv'))

    def test_uninspectable_pid_denied(self):
        with patch.object(Path, 'read_bytes', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                r.ensure_simulator_gone(dict(pid=123, image='/x/simv'))

    def test_cache_finish_both_logs_required(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(r.checker, 'check_log'):
            d = Path(tmp)
            log = '$finish called from file "ara_tb.sv"\nV C S   S i m u l a t i o n   R e p o r t\nTime: 2000 fs\n'
            for f in ('console.log', 'run.vcs.log'):
                (d / f).write_text(log)
            self.assertEqual(r.normal_finish(d), 2000)
            (d / 'run.vcs.log').write_text('Core Test *** SUCCESS ***\n')
            with self.assertRaisesRegex(RuntimeError, 'did not finish normally'):
                r.normal_finish(d)


if __name__ == '__main__':
    unittest.main()
