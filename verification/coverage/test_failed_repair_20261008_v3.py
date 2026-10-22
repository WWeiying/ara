"""Offline contract tests only: no simulator, converter, compiler, or service."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import run_failed_repair_20261008_v3 as runner


class ReuseContracts(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.previous = self.root / 'acceptance03'
        self.image_dir = self.root / 'build02'
        self.image = self.image_dir / 'sim/simv'
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b'fixed simulator identity; not executable')
        self.rtl = self.root / 'frozen.sv'
        self.rtl.write_text('module frozen; endmodule\n')
        self.fixture = self.root / 'fixture'
        self.fixture.mkdir()
        (self.fixture / 'input.elf').write_bytes(b'exact original ELF')
        self.save(self.image_dir / 'build-status.json', {'status': 'PASS'})
        self.save(self.image_dir / 'build-image.json', runner.base.pins([self.image]))
        self.save(self.image_dir / 'build-source-pins.json', runner.base.pins([self.rtl]))
        self.previous.mkdir()
        self.save(self.previous / 'source-pins.json', runner.base.pins(
            [self.image, self.rtl, Path(runner.legacy.__file__)]))
        self.state = dict(status='STOPPED', total=23,
            cases={n: dict(status='QUEUED') for n in runner.FOCUSED + runner.NEIGHBOURS})
        self.save(self.previous / 'status.json', self.state)
        self.stack.enter_context(patch.object(runner, 'PREVIOUS', self.previous))
        self.stack.enter_context(patch.object(runner.legacy, 'source', return_value=self.fixture))
        self.stack.enter_context(patch.object(runner.legacy, 'simulation_command',
            side_effect=lambda image, directory, name: [str(image), '+PRELOAD=' + str(directory / 'input.elf')]))
        self.stack.enter_context(patch.object(runner.legacy, 'check_real_uvm_log',
            return_value={'status': 'PASS', 'issues': []}))
        self.stack.enter_context(patch.object(runner.legacy.operands, 'check_contract_log', return_value=[]))
        self.audit = self.stack.enter_context(patch.object(runner, 'LEGACY_AUDIT',
            return_value={'status': 'PASS', 'strict_check': True}))
        self.qbs = self.stack.enter_context(patch.object(runner, 'verify_qbs_receipt',
            return_value={'status': 'PASS', 'strict_check': True}))
        # Any subprocess invocation is a test failure, including EDA tools.
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('no subprocess allowed')))
        self.stack.enter_context(patch('subprocess.run', side_effect=AssertionError('no subprocess allowed')))

    def save(self, path, data):
        runner.base.save(path, data)

    def case(self, name='mask_restart', status='PASS', reason=None):
        self.name = name
        self.old = self.previous / 'results' / name
        self.old.mkdir(parents=True)
        self.target = self.root / 'new' / name
        self.target.mkdir(parents=True)
        for d in (self.old, self.target):
            shutil.copyfile(self.fixture / 'input.elf', d / 'input.elf')
        log = ('Core Test *** SUCCESS *** (tohost = 0)\n'
               '$finish called from file "' + str(runner.ROOT / 'hardware/tb/ara_commit_monitor.sv') + '", line 270.\n'
               '[ARA_CONTRACT] requests=5 responses=5 exceptions=0 mmu_request_cycles=0 '
               'protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n'
               'V C S   S i m u l a t i o n   R e p o r t\n'
               'Time: 20000000 fs\n')
        for filename in ('console.log', 'run.vcs.log'):
            (self.old / filename).write_text(log)
        (self.old / 'commit_trace.csv').write_text('cycle\n10\n')
        (self.old / 'vector_trace.csv').write_text('fixture vector evidence\n')
        command = runner.legacy.simulation_command(self.image, self.old, name)
        self.save(self.old / 'started.json', dict(pid=123, image=str(self.image),
            image_sha256=runner.base.sha256(self.image),
            elf_sha256=runner.base.sha256(self.old / 'input.elf'), command=command))
        self.save(self.old / 'command.json', dict(command=command, cwd=str(self.old), timeout_s=1800))
        self.receipt = dict(status=status, directory=str(self.old), elapsed_s=1.0)
        if reason is not None:
            self.receipt['reason'] = reason
        self.write_receipt()

    def write_receipt(self):
        self.save(self.old / 'audit.json', self.receipt)
        self.state['cases'][self.name] = self.receipt
        self.save(self.previous / 'status.json', self.state)

    def reuse(self):
        return runner.reuse_pass(self.target, self.name, self.previous, self.image, self.image_dir)

    def known_failure(self):
        self.case('qbs_canonical', 'FAIL', runner.QBS_REASON)
        self.stack.enter_context(patch.object(runner, 'QBS_FAILURE_SHA',
                                              runner.base.sha256(self.old / 'audit.json')))

    def test_bounded_scope_and_prepare_default_never_launches(self):
        self.assertEqual((len(runner.FOCUSED), len(runner.NEIGHBOURS)), (6, 17))
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(runner.main([]), 0)
        self.assertIn('PREPARED_ONLY', stream.getvalue())

    def test_fresh_qbs_dispatch_never_calls_old_checker(self):
        self.case('qbs_canonical')
        new_result = {'status': 'PASS', 'qualified_checker': 'v2'}
        calls = []
        def new_audit(directory, output=None):
            calls.append((directory, output))
            return new_result
        self.audit.side_effect = AssertionError('old checker must never see QBS')
        with patch.object(runner, 'checker', return_value=SimpleNamespace(audit=new_audit)), \
             patch.object(runner, 'completed_logs', return_value={'status': 'PASS'}):
            self.assertEqual(runner.audit(self.target, 'qbs_canonical'), new_result)
        self.assertEqual(calls, [(self.target, self.target / 'qbs-canonical-audit-v3')])
        self.audit.assert_not_called()
        self.qbs.assert_not_called()

    def test_fresh_fof_dispatch_never_calls_old_checker(self):
        new_result = {'status': 'PASS', 'checker': 'audit_fof_repair_v2'}
        calls = []
        def new_audit(directory):
            calls.append(directory)
            return new_result
        self.audit.side_effect = AssertionError('old checker must never see FOF')
        with patch.object(runner, 'fof_checker', return_value=SimpleNamespace(audit=new_audit)), \
             patch.object(runner, 'completed_logs', return_value={'status': 'PASS'}):
            self.assertEqual(runner.audit(self.root, 'vgap112_sv39_fof'), new_result)
        self.assertEqual(calls, [self.root])
        self.audit.assert_not_called()

    def test_fof_nonpass_rejected(self):
        with patch.object(runner, 'fof_checker', return_value=SimpleNamespace(
                audit=lambda directory: {'status': 'FAIL'})), \
             patch.object(runner, 'completed_logs', return_value={'status': 'PASS'}):
            with self.assertRaisesRegex(RuntimeError, 'strict FOF successor audit failed'):
                runner.audit(self.root, 'vgap112_sv39_fof')

    def test_fof_unconfirmed_hash_blocks_execution(self):
        with patch.object(runner, 'FOF_CHECKER_SHA', None), patch.object(runner, 'checker'), \
             patch.object(runner.legacy, 'main') as dispatch:
            with self.assertRaisesRegex(RuntimeError, 'awaits Ampere'):
                runner.main(['--execute'])
        dispatch.assert_not_called()

    def test_new_image_main_uses_successor_global_hooks_without_previous_output(self):
        args = ['--image-directory', str(self.image_dir), '--output', str(self.root / 'fresh')]
        original_audit, original_reuse = runner.legacy.audit, runner.legacy.reuse_pass
        def dispatch():
            fof.assert_called_once_with()
            self.assertIs(runner.legacy.audit, runner.audit)
            self.assertIs(runner.legacy.reuse_pass, runner.reuse_pass)
            self.assertEqual(runner.sys.argv[1:], args)
            self.assertNotIn('--previous-output', runner.sys.argv)
            return 0
        with patch.object(runner.legacy, 'main', side_effect=dispatch) as main, \
             patch.object(runner, 'checker'), patch.object(runner, 'fof_checker') as fof:
            self.assertEqual(runner.main(['--execute', *args]), 0)
        main.assert_called_once_with()
        self.assertIs(runner.legacy.audit, original_audit)
        self.assertIs(runner.legacy.reuse_pass, original_reuse)

    def test_successor_global_hooks_restored_after_error(self):
        original_audit, original_reuse = runner.legacy.audit, runner.legacy.reuse_pass
        with patch.object(runner.legacy, 'main', side_effect=RuntimeError('controlled stop')), \
             patch.object(runner.legacy, 'ACTIVE_OUTPUT', None), patch.object(runner, 'checker'), \
             patch.object(runner, 'fof_checker'):
            with self.assertRaisesRegex(RuntimeError, 'controlled stop'):
                runner.main(['--execute'])
        self.assertIs(runner.legacy.audit, original_audit)
        self.assertIs(runner.legacy.reuse_pass, original_reuse)

    def test_same_build_pass_reaudited_without_mutating_old_files(self):
        self.case()
        before = runner.base.inventory(self.old)
        result = self.reuse()
        self.assertEqual(result['status'], 'PASS')
        self.assertFalse(result['simulation_launched'])
        self.assertFalse(result['simulator_process_exit_verified'])
        self.audit.assert_called_once_with(self.target, self.name)
        self.assertEqual(before, runner.base.inventory(self.old))
        self.assertFalse((self.target / 'run.vcs.log').is_symlink())
        self.assertFalse((self.target / 'code.vdb').exists())

    def test_exact_qbs_checker_failure_can_be_offline_reclassified(self):
        self.known_failure()
        before = (self.old / 'audit.json').read_bytes()
        result = self.reuse()
        self.assertTrue(result['checker_error_reclassified'])
        self.assertEqual(result['previous_status'], 'FAIL')
        self.qbs.assert_called_once()
        self.audit.assert_not_called()
        self.assertEqual((self.old / 'audit.json').read_bytes(), before)

    def test_qbs_strict_checker_failure_blocks_reclassification(self):
        self.known_failure()
        self.qbs.side_effect = ValueError('real numerical mismatch')
        with self.assertRaisesRegex(ValueError, 'numerical'):
            self.reuse()
        self.assertEqual(runner.base.read(self.old / 'audit.json')['status'], 'FAIL')

    def test_qbs_returned_nonpass_also_rejected(self):
        self.known_failure()
        self.qbs.return_value = {'status': 'FAIL'}
        with self.assertRaisesRegex(RuntimeError, 'strict successor'):
            self.reuse()

    def test_other_failure_with_identical_reason_rejected(self):
        self.case('vgap112_sv39_fof', 'FAIL', runner.QBS_REASON)
        with self.assertRaisesRegex(RuntimeError, 'previous case did not pass'):
            self.reuse()

    def test_qbs_other_failure_rejected(self):
        self.case('qbs_canonical', 'FAIL', 'ValueError: numerical mismatch')
        with self.assertRaisesRegex(RuntimeError, 'previous case did not pass'):
            self.reuse()

    def test_qbs_same_reason_but_unpinned_receipt_rejected(self):
        self.case('qbs_canonical', 'FAIL', runner.QBS_REASON)
        with self.assertRaisesRegex(RuntimeError, 'previous case did not pass'):
            self.reuse()

    def test_timeouts_rejected(self):
        self.case('vgap112_sv39_fof', 'TIMEOUT', 'TimeoutExpired')
        with self.assertRaisesRegex(RuntimeError, 'previous case did not pass'):
            self.reuse()

    def test_incomplete_case_not_automatically_retried(self):
        self.case()
        (self.old / 'audit.json').unlink()
        with self.assertRaisesRegex(RuntimeError, 'incomplete evidence'):
            self.reuse()

    def test_only_never_started_queued_case_can_launch_later(self):
        self.name = 'axpy'
        self.target = self.root
        self.assertIsNone(self.reuse())

    def test_nonterminal_previous_campaign_rejected(self):
        self.case()
        self.state['status'] = 'RUNNING'
        self.save(self.previous / 'status.json', self.state)
        with self.assertRaisesRegex(RuntimeError, 'not terminal'):
            self.reuse()

    def test_changed_fof_source_with_same_image_rejected(self):
        self.case()
        self.rtl.write_text('module new_fof; endmodule\n')
        with self.assertRaisesRegex(RuntimeError, 'frozen input changed'):
            self.reuse()

    def test_new_build_manifest_cannot_reuse_old_image(self):
        self.case()
        self.rtl.write_text('module repaired_fof; endmodule\n')
        self.save(self.image_dir / 'build-source-pins.json', runner.base.pins([self.rtl]))
        with self.assertRaisesRegex(RuntimeError, 'same build/source'):
            self.reuse()

    def test_build_not_complete_rejected(self):
        self.case()
        self.save(self.image_dir / 'build-status.json', {'status': 'BUILDING'})
        with self.assertRaisesRegex(RuntimeError, 'completed source-checked'):
            self.reuse()

    def test_changed_simulator_rejected(self):
        self.case()
        self.image.write_bytes(b'other simulator')
        with self.assertRaisesRegex(RuntimeError, 'frozen input changed'):
            self.reuse()

    def test_wrong_original_elf_rejected(self):
        self.case()
        (self.old / 'input.elf').write_bytes(b'wrong ELF')
        with self.assertRaisesRegex(RuntimeError, 'ELF differs'):
            self.reuse()

    def test_changed_launch_command_rejected(self):
        self.case()
        launch = runner.base.read(self.old / 'started.json')
        launch['command'].append('+IGNORE_ERRORS')
        self.save(self.old / 'started.json', launch)
        with self.assertRaisesRegex(RuntimeError, 'launch command'):
            self.reuse()

    def test_launch_directory_forgery_rejected(self):
        self.case()
        command = runner.base.read(self.old / 'command.json')
        command['cwd'] = str(self.fixture)
        self.save(self.old / 'command.json', command)
        with self.assertRaisesRegex(RuntimeError, 'unbound launch'):
            self.reuse()

    def test_partial_success_log_without_finish_rejected(self):
        self.case()
        (self.old / 'console.log').write_text('Core Test *** SUCCESS ***\n')
        with self.assertRaisesRegex(RuntimeError, 'normal simulator finish'):
            self.reuse()

    def test_mismatched_finish_timestamps_rejected(self):
        self.case()
        path = self.old / 'console.log'
        path.write_text(path.read_text().replace('20000000', '21000000'))
        with self.assertRaisesRegex(RuntimeError, 'timestamps differ'):
            self.reuse()

    def test_trace_after_finish_rejected(self):
        self.case()
        (self.old / 'commit_trace.csv').write_text('cycle\n30\n')
        with self.assertRaisesRegex(RuntimeError, 'trace extends'):
            self.reuse()

    def test_protocol_failure_rejected(self):
        self.case('qbs_canonical')
        runner.legacy.check_real_uvm_log.return_value = {'status': 'FAIL', 'issues': ['response mismatch']}
        with self.assertRaisesRegex(RuntimeError, 'protocol failure'):
            self.reuse()

    def test_do_not_copy_writable_old_audit_outputs(self):
        self.case()
        (self.old / 'scalar-comparison.json').write_text('original sealed result')
        self.reuse()
        self.assertFalse((self.target / 'scalar-comparison.json').exists())
        self.assertEqual((self.old / 'scalar-comparison.json').read_text(), 'original sealed result')

    def test_original_mutation_during_checker_is_detected(self):
        self.case()
        def mutate(*args):
            (self.old / 'console.log').write_text('unexpected modification')
            return {'status': 'PASS'}
        self.audit.side_effect = mutate
        with self.assertRaisesRegex(RuntimeError, 'frozen input changed'):
            self.reuse()

    def inherited_case(self):
        self.case()
        origin = self.root / 'verification/out/failed-repair-acceptance-20261008-02'
        launched = origin / 'results' / self.name
        launched.mkdir(parents=True)
        for path in self.old.iterdir():
            shutil.copyfile(path, launched / path.name)
        command = runner.legacy.simulation_command(self.image, launched, self.name)
        started = runner.base.read(launched / 'started.json')
        started['command'] = command
        self.save(launched / 'started.json', started)
        self.save(launched / 'command.json', dict(command=command, cwd=str(launched), timeout_s=1800))
        v1 = self.root / 'verification/coverage/run_failed_repair_20261008.py'
        v1.parent.mkdir(parents=True)
        shutil.copyfile(runner.ROOT / 'verification/coverage/run_failed_repair_20261008.py', v1)
        self.save(origin / 'source-pins.json', runner.base.pins([self.image, self.rtl, v1]))
        for name in ('started.json', 'command.json'):
            (self.old / name).unlink()
            (self.old / name).symlink_to(launched / name)
        self.receipt['reused_completed_same_image'] = str(launched)
        self.receipt['evidence_pins'] = runner.base.pins(p for p in launched.iterdir() if p.is_file())
        self.write_receipt()
        self.stack.enter_context(patch.object(runner, 'ROOT', self.root))
        for filename in ('console.log', 'run.vcs.log'):
            path = self.old / filename
            path.write_text(path.read_text().replace(str(Path(runner.legacy.__file__).resolve().parents[2]),
                                                   str(self.root)))
        return launched

    def test_acceptance03_inherited_acceptance02_pass_is_bound(self):
        self.inherited_case()
        self.assertEqual(self.reuse()['status'], 'PASS')

    def test_inherited_source_drift_rejected(self):
        launched = self.inherited_case()
        pins = runner.base.read(launched.parent.parent / 'source-pins.json')
        pins[str(self.image)] = '0' * 64
        self.save(launched.parent.parent / 'source-pins.json', pins)
        with self.assertRaisesRegex(RuntimeError, 'inherited evidence is not the same build'):
            self.reuse()


class ActualQbsOfflineContracts(unittest.TestCase):
    def test_actual_checker_import_is_v2_not_sealed_v1(self):
        self.assertEqual(runner.checker().__name__, 'audit_qbs_canonical_repair_v2')

    def test_real_both_terminal_contracts(self):
        for name in ('qbs_canonical', 'mask_restart', 'vgap76_red16',
                     'vgap101_illegal_segment_store', 'vmemory_emul_r2_boundary_reject'):
            with self.subTest(name=name):
                result = runner.completed_logs(runner.PREVIOUS / 'results' / name, name)
                self.assertEqual(result['status'], 'PASS')

    def test_qualified_real_receipt_replays_without_any_subprocess(self):
        original = runner.PREVIOUS / 'results/qbs_canonical'
        with tempfile.TemporaryDirectory() as tmp, \
             patch('subprocess.run', side_effect=AssertionError('no EDA/converter allowed')), \
             patch('subprocess.Popen', side_effect=AssertionError('no EDA/converter allowed')):
            result = runner.verify_qbs_receipt(original, runner.QBS_RECEIPT, Path(tmp) / 'audit')
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['stdout']['checks'], 160)
        self.assertEqual(result['cycles']['sampled_edges'], 295)
        self.assertEqual(result['cycles']['last_core_cycle'], 147935)
        self.assertFalse(result['per_beat_protocol_certified'])

    def test_changed_qualified_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'receipt.json'
            path.write_text('{"status":"PASS"}')
            with self.assertRaisesRegex(RuntimeError, 'qualified QBS receipt changed'):
                runner.verify_qbs_receipt(runner.PREVIOUS / 'results/qbs_canonical', path, Path(tmp) / 'audit')

    def test_data_not_described_by_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / 'input.elf').write_bytes(b'wrong binary')
            with self.assertRaisesRegex(RuntimeError, 'exact artifacts'):
                runner.verify_qbs_receipt(directory, runner.QBS_RECEIPT, directory / 'audit')


if __name__ == '__main__':
    unittest.main()
