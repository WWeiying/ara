"""Offline reuse/dispatch tests; no simulator, converter, compiler or service."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_failed_repair_20261008_v4 as r


class Reuse(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.old = self.root / 'acceptance04'
        self.image_dir = self.root / 'build03'
        self.image = self.image_dir / 'sim/simv'
        self.image.parent.mkdir(parents=True)
        self.image.write_bytes(b'non-executable image fixture')
        self.rtl = self.root / 'rtl.sv'
        self.rtl.write_text('module frozen; endmodule\n')
        self.fixture = self.root / 'fixture'
        self.fixture.mkdir()
        (self.fixture / 'input.elf').write_bytes(b'exact ELF')
        (self.fixture / 'spike.trace').write_text('independent reference\n')
        for key, value in [('build-status.json', {'status': 'PASS'}),
                           ('build-image.json', r.base.pins([self.image])),
                           ('build-source-pins.json', r.base.pins([self.rtl]))]:
            r.base.save(self.image_dir / key, value)
        self.old.mkdir()
        r.base.save(self.old / 'source-pins.json', r.base.pins(
            [self.image, self.rtl, Path(r.prior.__file__), Path(r.legacy.__file__)]))
        self.state = dict(status='STOPPED', total=23,
            cases={n: {'status': 'QUEUED'} for n in r.prior.EXPECTED_SCOPE})
        self.patch(r, 'PREVIOUS', self.old)
        self.patch(r, 'IMAGE_DIR', self.image_dir)
        self.patch(r.legacy, 'source', return_value=self.fixture)
        self.patch(r.legacy, 'simulation_command', side_effect=lambda image, d, n:
                   [str(image), '+PRELOAD=' + str(d / 'input.elf')])
        self.patch(r.legacy.operands, 'check_contract_log', return_value=[])
        self.patch(r.legacy, 'check_real_uvm_log', return_value={'status': 'PASS'})
        for name in r.FOCUSED:
            d = self.old / 'results' / name
            d.mkdir(parents=True)
            for file in ('input.elf', 'spike.trace'):
                shutil.copyfile(self.fixture / file, d / file)
            log = ('Core Test *** SUCCESS *** (tohost = 0)\n$finish called from file "' +
                   str(r.ROOT / 'hardware/tb/ara_commit_monitor.sv') + '", line 270.\n'
                   '[ARA_CONTRACT] requests=5 responses=5 exceptions=0 mmu_request_cycles=0 '
                   'protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n'
                   'V C S   S i m u l a t i o n   R e p o r t\nTime: 20000000 fs\n')
            for file in ('console.log', 'run.vcs.log'):
                (d / file).write_text(log)
            (d / 'commit_trace.csv').write_text('cycle\n10\n')
            (d / 'vector_trace.csv').write_text('native trace\n')
            (d / 'trace_hart_0.log').write_text('tracer\n')
            command = r.legacy.simulation_command(self.image, d, name)
            r.base.save(d / 'started.json', dict(pid=1, image=str(self.image),
                image_sha256=r.base.sha256(self.image), elf_sha256=r.base.sha256(d / 'input.elf'),
                command=command))
            r.base.save(d / 'command.json', dict(command=command, cwd=str(d), timeout_s=1800))
            self.state['cases'][name] = dict(status='PASS', directory=str(d), elapsed_s=1)
            r.base.save(d / 'audit.json', self.state['cases'][name])
        fof = self.old / 'results' / r.FOF
        self.state['cases'][r.FOF].update(status='FAIL', reason=r.FOF_REASON)
        r.base.save(fof / 'audit.json', self.state['cases'][r.FOF])
        self.patch(r, 'FOF_FAILURE_SHA', r.base.sha256(fof / 'audit.json'))
        r.base.save(self.old / 'status.json', self.state)
        self.target = self.root / 'new'
        self.target.mkdir()
        self.strict = dict(status='PASS', case=r.FOF, elf_sha256=r.base.sha256(fof / 'input.elf'),
            scalar={'matched_instructions': 83732}, scalar_memory={'instructions': 83732},
            footprint={'checks': 2294}, native={'defined_compared_bytes': 684},
            lifecycle={'requests': 38}, tracer={'handler_mtval': 0}, checker='audit_fof_repair_v3')
        self.fof_audit = self.patch(r, 'fof_checker', return_value=SimpleNamespace(
            __file__=str(self.rtl), base=SimpleNamespace(CASE=r.FOF), audit=lambda d: self.strict))
        self.patch(r, 'FOF_CHECKER_SHA', r.base.sha256(self.rtl))
        self.receipt = dict(self.strict, directory=str(fof),
            original_failure_receipt=str(fof / 'audit.json'), original_failure_receipt_sha256=r.FOF_FAILURE_SHA,
            input_pins=r.base.pins([self.rtl, *[fof / n for n in r.FOF_INPUTS]]))
        self.receipt_path = self.root / 'qualified.json'
        r.base.save(self.receipt_path, self.receipt)
        self.patch(r, 'FOF_RECEIPT', self.receipt_path)
        self.patch(r, 'FOF_RECEIPT_SHA', r.base.sha256(self.receipt_path))
        self.old_audit = self.patch(r.prior, 'audit', return_value={'status': 'PASS'})
        self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('no subprocess')))
        self.stack.enter_context(patch('subprocess.run', side_effect=AssertionError('no subprocess')))

    def patch(self, obj, name, *args, **kwargs):
        return self.stack.enter_context(patch.object(obj, name, *args, **kwargs))

    def reuse(self, name):
        d = self.target / name
        d.mkdir(exist_ok=True)
        for file in ('input.elf', 'spike.trace'):
            if not (d / file).exists():
                shutil.copyfile(self.fixture / file, d / file)
        return r.reuse_pass(d, name, self.old, self.image, self.image_dir)

    def change_receipt(self, name, **changes):
        self.state['cases'][name].update(changes)
        r.base.save(self.old / 'results' / name / 'audit.json', self.state['cases'][name])
        r.base.save(self.old / 'status.json', self.state)

    def test_all_six_reused_no_simulator_and_original_fail_preserved(self):
        before = r.base.pins(p for p in self.old.rglob('*') if p.is_file())
        for name in r.FOCUSED:
            with self.subTest(name=name):
                result = self.reuse(name)
                self.assertEqual(result['status'], 'PASS')
                self.assertFalse(result['simulation_launched'])
                self.assertEqual(result['checker_error_reclassified'], name == r.FOF)
        self.assertEqual(self.old_audit.call_count, 5)
        r.base.check(before)
        self.assertEqual(r.base.read(self.old / 'results' / r.FOF / 'audit.json')['status'], 'FAIL')

    def test_new_qbs_directory_omits_old_audit_and_vdb(self):
        old = self.old / 'results/qbs_canonical'
        (old / 'qbs-canonical-audit-v3').mkdir()
        (old / 'code.vdb').mkdir()
        self.reuse('qbs_canonical')
        d = self.target / 'qbs_canonical'
        self.assertTrue((d / 'console.log').is_symlink())
        self.assertFalse((d / 'audit.json').exists())
        self.assertFalse((d / 'code.vdb').exists())
        self.assertFalse((d / 'qbs-canonical-audit-v3').exists())
        self.old_audit.assert_called_once_with(d, 'qbs_canonical')

    def test_missing_original_never_returns_none(self):
        (self.old / 'results/mask_restart/audit.json').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing completed original'):
            self.reuse('vgap76_red16')

    def test_other_fail_rejected(self):
        self.change_receipt('qbs_canonical', status='FAIL', reason=r.prior.QBS_REASON)
        with self.assertRaisesRegex(RuntimeError, 'unqualified FAIL'):
            self.reuse('qbs_canonical')

    def test_changed_fof_reason_rejected(self):
        self.change_receipt(r.FOF, reason='real architectural mismatch')
        with self.assertRaisesRegex(RuntimeError, 'unqualified FAIL'):
            self.reuse(r.FOF)

    def test_changed_failure_hash_rejected(self):
        self.change_receipt(r.FOF, elapsed_s=2)
        with self.assertRaisesRegex(RuntimeError, 'unqualified FAIL'):
            self.reuse(r.FOF)

    def test_missing_receipt_blocks_fof(self):
        self.patch(r, 'FOF_RECEIPT', None)
        with self.assertRaisesRegex(RuntimeError, 'receipt path and SHA'):
            self.reuse(r.FOF)

    def test_receipt_hash_change_rejected(self):
        self.receipt_path.write_text('{}')
        with self.assertRaisesRegex(RuntimeError, 'receipt changed'):
            self.reuse(r.FOF)

    def test_receipt_qualified_pass_not_sufficient_if_strict_recheck_fails(self):
        self.strict['status'] = 'FAIL'
        with self.assertRaisesRegex(RuntimeError, 'strict FOF v3'):
            self.reuse(r.FOF)

    def test_receipt_recheck_disagreement_rejected(self):
        self.strict['tracer'] = {'handler_mtval': 1}
        with self.assertRaisesRegex(RuntimeError, 'disagrees.*tracer'):
            self.reuse(r.FOF)

    def test_wrong_receipt_source_rejected(self):
        self.receipt['directory'] = str(self.root / 'acceptance03')
        r.base.save(self.receipt_path, self.receipt)
        self.patch(r, 'FOF_RECEIPT_SHA', r.base.sha256(self.receipt_path))
        with self.assertRaisesRegex(RuntimeError, 'not acceptance04'):
            self.reuse(r.FOF)

    def test_queued_neighbour_only_can_dispatch(self):
        self.assertIsNone(self.reuse(r.NEIGHBOURS[0]))

    def test_partial_neighbour_rejected(self):
        d = self.old / 'results' / r.NEIGHBOURS[0]
        d.mkdir()
        (d / 'console.log').write_text('partial')
        with self.assertRaisesRegex(RuntimeError, 'incomplete previous attempt'):
            self.reuse(r.NEIGHBOURS[0])

    def test_new_build_rejected(self):
        self.image.write_bytes(b'other image')
        with self.assertRaises(Exception):
            self.reuse('mask_restart')

    def test_source_drift_rejected(self):
        self.rtl.write_text('changed RTL')
        with self.assertRaises(Exception):
            self.reuse('mask_restart')

    def test_elf_drift_rejected(self):
        (self.old / 'results/mask_restart/input.elf').write_bytes(b'wrong ELF')
        with self.assertRaisesRegex(RuntimeError, 'ELF differs'):
            self.reuse('mask_restart')

    def test_wrong_launch_rejected(self):
        p = self.old / 'results/mask_restart/command.json'
        value = r.base.read(p)
        value['timeout_s'] = 999
        r.base.save(p, value)
        with self.assertRaisesRegex(RuntimeError, 'command/timeout'):
            self.reuse('mask_restart')

    def test_success_without_finish_rejected(self):
        (self.old / 'results/mask_restart/console.log').write_text('Core Test *** SUCCESS ***\n')
        with self.assertRaisesRegex(RuntimeError, 'finish/report'):
            self.reuse('mask_restart')

    def test_protocol_error_rejected(self):
        p = self.old / 'results/mask_restart/console.log'
        p.write_text(p.read_text().replace('protocol_errors=0', 'protocol_errors=1'))
        with self.assertRaisesRegex(RuntimeError, 'protocol failure'):
            self.reuse('mask_restart')

    def test_destination_collision_rejected(self):
        d = self.target / 'qbs_canonical'
        d.mkdir()
        (d / 'qbs-canonical-audit-v3').mkdir()
        with self.assertRaisesRegex(RuntimeError, 'not fresh'):
            self.reuse('qbs_canonical')

    def test_nonterminal_campaign_rejected(self):
        self.state['status'] = 'RUNNING'
        r.base.save(self.old / 'status.json', self.state)
        with self.assertRaisesRegex(RuntimeError, 'not terminal'):
            self.reuse('mask_restart')

    def test_default_only_prepares(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(r.main([]), 0)
        self.assertIn('PREPARED_ONLY', out.getvalue())

    def test_main_preimports_and_installs_correct_auditor_before_pin_capture(self):
        order = []
        self.patch(r.prior, 'checker', side_effect=lambda: order.append('qbs-v2'))
        self.fof_audit.side_effect = lambda: order.append('fof-v3')
        self.patch(r, 'qualified_fof_receipt', return_value={})
        def dispatch():
            self.assertEqual(order[:2], ['qbs-v2', 'fof-v3'])
            self.assertIs(r.legacy.audit, r.audit)
            self.assertIs(r.legacy.reuse_pass, r.reuse_pass)
            return 0
        self.patch(r.legacy, 'main', side_effect=dispatch)
        self.assertEqual(r.main(['--execute', '--previous-output', str(self.old),
            '--wait-previous-unit', 'terminal.service', '--image-directory', str(self.image_dir)]), 0)


class RealSeals(unittest.TestCase):
    def test_real_checker_preimport_identity(self):
        with patch('subprocess.Popen', side_effect=AssertionError('no subprocess')), \
             patch('subprocess.run', side_effect=AssertionError('no subprocess')):
            self.assertEqual(r.fof_checker().__name__, 'audit_fof_repair_v3')
            self.assertEqual(r.base.sha256(Path(r.prior.__file__)), r.PRIOR_SHA)


if __name__ == '__main__':
    unittest.main()
