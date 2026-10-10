from contextlib import ExitStack
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import finalize_gap65_observed as f


def source_echo():
    lines = f.observed.OBSERVER.read_text().splitlines()
    return '\n'.join(['ucli% ' + x for x in lines[:3]] + lines[3:-1]) + '\n'


def passing_log():
    return source_echo() + '[DUT_BOUNDARY_CONTRACT] ready\n' + (
        'GAP65 traps=1 cause=5 tval=c0000000 pc=800016c8 '
        'fault_vrf=128 recovery_vrf=128 numerical=16 errors=0\n'
        'PASSED: qbs_gap65_late_fault checks=49 errors=0\n'
        'Core Test *** SUCCESS *** (tohost = 0)\n')


class EchoTests(unittest.TestCase):
    def test_exact_echo_original_checker_and_generic_runner(self):
        original = passing_log()
        normalized, record = f.echo.normalize(original, f.observed.OBSERVER.read_text())
        self.assertIn('FAILED:', original)
        self.assertNotIn('FAILED:', normalized)
        self.assertEqual(record['occurrences'], 1)
        self.assertIsNone(f.FAIL_RE.search(original))
        f.observed.checks.check_runtime_log(normalized, {'sites': {'gap65_fault_site': 0x800016c8}})

    def test_changed_missing_multiple_or_post_execution_echo_rejected(self):
        for text in (passing_log().replace('set root', 'set changed_root'),
                     passing_log().replace(source_echo(), ''),
                     source_echo() + passing_log(),
                     '[DUT_BOUNDARY_CONTRACT] ready\n' + passing_log()):
            with self.subTest(text=text[:80]), self.assertRaises(ValueError):
                f.echo.normalize(text, f.observed.OBSERVER.read_text())

    def test_failure_outside_echo_never_suppressed(self):
        for marker in ('FAILED: gap65 observer real error', 'FAILED: qbs_gap65_late_fault errors=2',
                       'Fatal: real assertion', 'Error: real error', 'puts "FAILED: forged"'):
            with self.subTest(marker=marker):
                normalized, _ = f.echo.normalize(passing_log() + marker + '\n',
                                                 f.observed.OBSERVER.read_text())
                self.assertIn(marker, normalized)
                with self.assertRaises(ValueError):
                    f.observed.checks.check_runtime_log(normalized, {'sites': {'gap65_fault_site': 0x800016c8}})

    def test_changed_source_shape_rejected(self):
        script = f.observed.OBSERVER.read_text().replace('    puts "FAILED:', '    puts "FAILED AGAIN:')
        with self.assertRaises(ValueError):
            f.echo.normalize(passing_log(), script)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        temporary = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(temporary)
        self.runtime = self.root / 'verification/out/gap65-late-fault-runtime-20261004-02'
        self.admission = self.root / 'verification/out/gap65-late-fault-preflight-20261004-05/admission.json'
        self.host = self.root / 'verification/out/gap65-late-fault-preflight-20261004-04'
        self.base = self.root / 'verification/out/gap67-current-20261004-01'
        self.artifact = f.artifact_at(self.runtime)
        self.work = self.artifact / 'work'
        self.vdb = self.work / 'code.vdb'
        self.work.mkdir(parents=True)
        sim = self.root / 'sim/simv'
        sim.parent.mkdir()
        sim.write_bytes(b'never execute')
        (sim.parent / 'simulator.conf').write_text('fixed configuration')
        self.elf = self.runtime / 'inputs' / (f.observed.NAME + '.elf')
        self.elf.parent.mkdir()
        self.elf.write_bytes(b'corrected ELF mock')
        (self.artifact / 'input.elf').write_bytes(self.elf.read_bytes())
        (self.runtime / 'inputs/simulator.conf').write_text('fixed configuration')
        self.sha = f.observed.sha(self.elf)
        self.write(self.admission, {'external': 'seal'})
        self.digest = f.observed.sha(self.admission)
        for name, value in [('ROOT', self.root), ('RUNTIME', self.runtime), ('ADMISSION', self.admission),
                            ('ADMISSION_SHA', self.digest), ('ELF_SHA', self.sha), ('BASELINE', self.base)]:
            self.stack.enter_context(patch.object(f, name, value))
        self.stack.enter_context(patch.object(f.observed, 'HOST', self.host))
        self.plan = dict(elf_sha256=self.sha, baseline=str(self.base), baseline_passed=650,
                         target=f.observed.checks.TARGET, observer=str(f.observed.OBSERVER),
                         simv=str(sim), image={str(sim): f.observed.sha(sim)},
                         design_vdb=str(self.root / 'design.vdb'), design_files={'mock': 'unused'},
                         files={str(f.observed.OBSERVER): f.observed.sha(f.observed.OBSERVER)})

        def verify(path, digest):
            proof = f.evidence.Evidence()
            proof.pin(path, digest)
            proof.hashes(self.plan['files'])
            return self.plan, proof.files
        self.verify = self.stack.enter_context(patch.object(f.observed, 'verify_plan', side_effect=verify))
        self.rejection = dict(status='REJECTED', reason='runtime failure', aggregate_admitted=False, retry_allowed=False)
        self.write(self.runtime / 'rejected.json', self.rejection)
        self.summary = dict(name=f.observed.CASE, kind='app', status='PASS', returncode=0,
                            artifact_dir=str(self.artifact), reason='', elapsed_s=1)
        self.write(self.runtime / 'results/summary.json', [self.summary])
        self.write(self.runtime / 'results/run.json', dict(status='COMPLETE', source_snapshot={'sha256': self.digest},
                   input_snapshots=True, commit_trace=True, timeout_s=300, invocation=['mock']))
        self.write(self.runtime / 'runtime.json', dict(admission=str(self.admission), admission_sha256=self.digest,
                   files=f.full.pins([self.elf, self.runtime / 'inputs/simulator.conf'])))
        wrapper = self.runtime / 'inputs/observed_simv'
        wrapper.write_text('#!/bin/sh\nexec ' + shlex.join(['/usr/bin/python3', '-B', str(f.observed.SCRIPT),
            '--sim-exec', str(self.runtime / 'runtime.json'), '--config-sha256',
            f.observed.sha(self.runtime / 'runtime.json'), '--']) + ' "$@"\n')
        self.wrapper_image = f.full.batch.simulation_image(wrapper)
        self.write(self.artifact / 'inputs.json', dict(simv={'path': str(wrapper), 'image_sha256': self.wrapper_image},
            binary={'path': str(self.artifact / 'input.elf'), 'sha256': self.sha}))
        self.write(self.host / 'elf-proof.json', dict(elf_sha256=self.sha, sites={'gap65_fault_site': 0x800016c8}))
        for path in (self.artifact / 'console.log', self.work / 'run.vcs.log'):
            path.write_text(passing_log())
        before = dict(zip(f.observed.FIELDS, [0, 1, 6703, 3, 10, 1, 4, 5, 1, 0, 1, 1, 1, 0, 0]))
        after = dict(before, cycle=6704, state=10)
        transcript = '\t'.join(['phase', *f.observed.FIELDS]) + '\n'
        for phase, row in [('before', before), ('after', after)]:
            transcript += '\t'.join([phase, *[str(row[x]) for x in f.observed.FIELDS]]) + '\n'
        (self.work / 'gap65-observer.tsv').write_text(transcript + 'END\n')
        self.command = [str(sim), '-ucli', '-do', str(f.observed.OBSERVER), '-no_save',
                        *f.observed.expected_args(self.runtime), '-cm', f.full.base.METRICS,
                        '-cm_dir', str(self.vdb), '-cm_name', f.observed.NAME]
        self.write(self.work / 'coverage.command.json', dict(command=self.command, cwd=str(self.work)))
        data = self.vdb / 'snps/coverage/db/testdata' / f.observed.NAME
        data.mkdir(parents=True)
        (data / 'fsm.verilog.data.xml').write_text('<covdata/>')
        self.vdb_files = f.full.base.inventory(self.vdb)
        self.valid_vdb = self.stack.enter_context(patch.object(f.full.batch, 'valid_vdb', return_value=self.vdb_files))
        self.xml = ET.Element('root')
        ET.SubElement(self.xml, 'srctest', cmdline=shlex.join(self.command))
        self.stack.enter_context(patch.object(f.full.batch, 'xml_root', return_value=self.xml))
        self.raw_before = dict(checksum='2676500856', width=43, bits='0x0')
        self.raw_after = dict(self.raw_before, bits=hex(1 << 27))
        self.metric = self.stack.enter_context(patch.object(f.observed.bitmaps, 'read_metric',
                                      return_value={f.observed.checks.TARGET_SCOPE: self.raw_after}))
        self.write(self.base / 'combined-bits.json', dict(metrics={'fsm': {f.observed.checks.TARGET_SCOPE: self.raw_before}}))
        self.audit = dict(status='PASS', errors=[], case_count=1, passed_cases=1, failed_cases=0,
                          cases=[dict(status='PASS', name=f.observed.CASE, errors=[], artifact_dir=str(self.artifact))],
                          policy=dict(require_complete=True, require_trace=True))
        self.audit_call = self.stack.enter_context(patch.object(f.observed, 'audit_run', return_value=self.audit))
        self.spawn = self.stack.enter_context(patch('subprocess.Popen', side_effect=AssertionError('no child')))
        self.exec = self.stack.enter_context(patch.object(os, 'execv', side_effect=AssertionError('no exec')))

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, sort_keys=True))

    def check(self):
        return f.validate_runtime(self.runtime, self.admission, self.digest, f.evidence.Evidence())

    def test_recovery_reaudits_without_original_result_or_audit(self):
        _, result, _, audit, _ = self.check()
        self.assertEqual(result['status'], 'PASS_POSTPROCESS_RECOVERY')
        self.assertEqual(audit, self.audit)
        self.audit_call.assert_called_once_with(self.runtime / 'results', require_trace=True)
        self.valid_vdb.assert_called_once_with(self.vdb, f.observed.NAME, self.plan['simv'])
        self.assertEqual(f.full.read(self.runtime / 'rejected.json'), self.rejection)
        self.assertFalse((self.runtime / 'result.json').exists())
        self.assertFalse((self.runtime / 'independent_audit.json').exists())
        self.spawn.assert_not_called()
        self.exec.assert_not_called()

    def test_external_digest_and_fail01_excluded(self):
        with self.assertRaises(ValueError):
            f.validate_runtime(self.runtime, self.admission, '0' * 64, f.evidence.Evidence())
        with self.assertRaises(ValueError):
            f.validate_runtime(self.runtime.with_name('gap65-late-fault-runtime-20261004-01'),
                               self.admission, self.digest, f.evidence.Evidence())
        self.verify.assert_not_called()

    def test_only_exact_rejection_recoverable(self):
        for change in ({'reason': 'VDB drift'}, {'aggregate_admitted': True}, {'status': 'PASS'}):
            self.write(self.runtime / 'rejected.json', dict(self.rejection, **change))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check()

    def test_generic_fail_or_nonzero_result_not_relabeled(self):
        for change in ({'status': 'FAIL'}, {'returncode': 1}, {'name': 'app:foreign'},
                       {'artifact_dir': str(self.root)}):
            self.write(self.runtime / 'results/summary.json', [dict(self.summary, **change)])
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check()

    def test_actual_runtime_failure_rejected(self):
        (self.artifact / 'console.log').write_text(passing_log() + 'FAILED: actual observer error\n')
        with self.assertRaises(ValueError):
            self.check()

    def test_audit_failure_rejected(self):
        self.audit_call.return_value = dict(self.audit, status='FAIL')
        with self.assertRaises(RuntimeError):
            self.check()

    def test_observer_target_and_vdb_command_not_optional(self):
        (self.work / 'gap65-observer.tsv').write_text('partial\n')
        with self.assertRaises(ValueError):
            self.check()

    def test_no_target_gain_rejected(self):
        self.metric.return_value = {f.observed.checks.TARGET_SCOPE: self.raw_before}
        with self.assertRaises(ValueError):
            self.check()

    def test_foreign_vdb_command_rejected(self):
        self.xml.find('srctest').set('cmdline', shlex.join(self.command + ['-do', 'foreign.tcl']))
        with self.assertRaises(ValueError):
            self.check()

    def test_prepare_preserves_originals_and_records_versioned_recovery(self):
        proof = f.evidence.Evidence()
        source, result, summaries, audit, wrapper_image = f.validate_runtime(
            self.runtime, self.admission, self.digest, proof)
        checked = dict(proof=proof, admission=source, prior=dict(source, dve_outer_timeout_s=600,
                       dve_timeout_s=180), result=result, summaries=summaries, audit=audit,
                       wrapper_image=wrapper_image, rows=[{'name': 'old', 'vdb': '/old.vdb'}])
        originals = f.full.base.inventory(self.runtime / 'results')
        with patch.object(f, 'validate', return_value=checked):
            report = f.prepare(self.runtime, self.admission, self.digest)
        self.assertEqual(f.full.base.inventory(self.runtime / 'results'), originals)
        self.assertEqual(f.full.read(self.runtime / 'rejected.json'), self.rejection)
        self.assertFalse((self.runtime / 'result.json').exists())
        self.assertEqual(report['status'], 'CHECKED_PASS_REPORT_PENDING')
        row = f.full.read(self.runtime / 'outcomes/tests.json')
        self.assertEqual(row['kind'], f.KIND)
        self.assertEqual(row['vdb'], str(self.vdb))
        self.assertEqual(f.full.read(self.runtime / 'observed-recovery/result.json'), result)
        self.assertFalse((self.runtime / 'checkpoint.json').exists())
        self.assertFalse((self.runtime / 'collection.json').exists())
        with self.assertRaises(ValueError):
            f.prepare(self.runtime, self.admission, self.digest)
        self.spawn.assert_not_called()


class ProducerTests(unittest.TestCase):
    def test_hook_installation_is_explicit_and_idempotent(self):
        with patch.object(f.evidence.Evidence, 'baseline_row', f._NORMAL_ROW):
            f.install_hooks()
            f.install_hooks()
            self.assertIs(f.evidence.Evidence.baseline_row, f.baseline_row)

    def test_normal_rows_delegated_unchanged(self):
        proof, row, image, simv = object(), {'kind': 'directed'}, {'image': 'hash'}, '/simv'
        with patch.object(f, '_NORMAL_ROW', return_value='normal') as delegate:
            self.assertEqual(f.baseline_row(proof, row, image, simv), 'normal')
        delegate.assert_called_once_with(proof, row, image, simv)

    def test_foreign_versioned_case_rejected_before_io(self):
        with self.assertRaises(ValueError):
            f.baseline_row(object(), dict(kind=f.KIND, name='foreign', coverage_test=f.observed.NAME), {}, '/simv')

    def test_new_json_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'record.json'
            f.new_json(path, {'original': True})
            with self.assertRaises(FileExistsError):
                f.new_json(path, {'original': False})
            self.assertEqual(f.full.read(path), {'original': True})

    def test_scoped_report_callback_accepts_exact_command_without_launch(self):
        with tempfile.TemporaryDirectory() as directory, patch('subprocess.Popen',
                side_effect=AssertionError('no child')) as spawn:
            root = Path(directory)
            runtime, baseline, design = root / 'runtime', root / 'baseline', root / 'design.vdb'
            target = runtime / 'combined-dve'
            (target / 'DVEfiles').mkdir(parents=True)
            (baseline / 'combined-dve').mkdir(parents=True)
            design_xml = design / 'snps/coverage/db/design/verilog.design.xml'
            design_xml.parent.mkdir(parents=True)
            design_xml.write_text('<design/>')
            rows = [{'vdb': '/original/code.vdb', 'coverage_test': f.observed.NAME}]
            plan = dict(design_vdb=str(design), dve_timeout_s=180, dve_outer_timeout_s=600)
            inputs = str(design) + '\n/original/code.vdb\n'
            (target / 'inputs.txt').write_text(inputs)
            (runtime / 'combined-inputs.txt').write_text(inputs)
            (target / 'selected_tests.txt').write_text('/original/code/' + f.observed.NAME + '\n')
            (target / 'launcher.log').write_text('normal launcher\n')
            (target / 'DVEfiles/dve_gui.log').write_text('DVE_COVERAGE_EXPORT_DONE\n')
            (target / 'diagnostics.txt').write_text('')
            (target / 'summary.csv').write_text('Name,Depth,Line\nara_tb,0,50%\n')
            waiver = dict(status='NOT_APPLICABLE_UNREVIEWED_DESIGN', design_sha256=f.observed.sha(design_xml))
            for path in (target / 'waiver_status.json', baseline / 'combined-dve/waiver_status.json'):
                path.write_text(json.dumps(waiver))
            with patch.object(f, 'BASELINE', baseline):
                callback = f.report_callback(runtime, plan, rows, f.evidence.Evidence())
                command = ['bash', str(f.full.DVE / 'run_dve_coverage.sh'), str(target),
                           '--inputs-file', str(runtime / 'combined-inputs.txt')]
                environment = dict(DVE_COVERAGE_TIMEOUT='180', DVE_WAIVERS='auto')
                self.assertEqual(callback(command, runtime / 'logs/combined-dve.log', 600, environment), 0)
                with self.assertRaises(ValueError):
                    callback(command + ['override'], runtime / 'logs/combined-dve.log', 600, environment)
                (target / 'launcher.log').write_text('Error: unmappable database\n')
                with self.assertRaises(ValueError):
                    f.report_callback(runtime, plan, rows, f.evidence.Evidence())
            spawn.assert_not_called()


if __name__ == '__main__':
    unittest.main()
