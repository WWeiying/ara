"""Admission regressions; no compiler, simulator, DVE or systemd is executed."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import coverage_evidence as ev
import run_checked_extension as run

full = run.full


class CheckedExtensionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        return path

    def baseline(self, kind='directed'):
        directory = self.root / 'baseline'
        target = directory / 'results/old'
        artifact = target / 'tests/test'
        image_file = self.write(self.root / 'simv', 'image')
        image = full.pins([image_file])
        elf = self.write(artifact / 'input.elf', 'ELF')
        case = {'name': 'old', 'kind': kind, 'source_name': 'rvv:test',
                'frozen_elf': str(elf), 'elf_sha256': full.base.sha256(elf),
                'coverage_test': 'test', 'oracle': 'independent',
                'directed_test': {'kind': 'rvv'}, 'spike_sha256': '1' * 64,
                'seed': 1, 'watchdog_cycles': 1000}
        case['contract'] = full.contract(case)
        summary = self.write(target / 'summary.json',
                             [{'name': case['source_name'], 'status': 'PASS', 'artifact_dir': str(artifact)}])
        metadata = self.write(artifact / 'inputs.json',
                              {'simv': {'image_sha256': image}, 'binary': {'sha256': case['elf_sha256']},
                               'spike': {'sha256': case['spike_sha256']}})
        audit = self.write(target / 'independent_audit.json',
                           {'status': 'PASS', 'errors': [], 'case_count': 1, 'passed_cases': 1,
                            'failed_cases': 0, 'policy': dict.fromkeys(
                                ['require_complete', 'require_trace', 'require_vector', 'require_full_match'], True),
                            'cases': [{'name': case['source_name'], 'status': 'PASS', 'errors': [],
                                       'artifact_dir': str(artifact)}]})
        vdb = artifact / ('work/code.vdb' if kind == 'directed' else 'code.vdb')
        vdb.mkdir(parents=True)
        row = {'name': 'old', 'kind': kind, 'status': 'PASS', 'passed_only': True,
               'reused': False, 'vdb_valid': True, 'returncode': 0,
               'vdb': str(vdb), 'files': full.pins([summary, metadata, elf, audit]),
               'elf_sha256': case['elf_sha256'], 'coverage_test': 'test', 'contract': case['contract']}
        self.write(directory / 'outcomes/old.json', row)
        self.write(directory / 'all-outcomes.json', [row])
        reports = [self.write(directory / 'combined-dve' / name, 'report') for name in
                   ('summary.csv', 'inputs.txt', 'selected_tests.txt', 'waiver_status.json')]
        self.write(directory / 'combined-dve/inputs.txt', '/design.vdb\n' + str(vdb) + '\n')
        self.write(directory / 'collection.json',
                   {'status': 'PASS', 'passed': 1, 'image': image, 'reports': full.pins(reports)})
        plan = self.write(directory / 'plan.json', {'cases': [case], 'image': image,
                          'wrapper_image': image, 'simv': str(image_file), 'design_vdb': '/design.vdb'})
        self.write(directory / 'plan.sha256.json', full.pins([plan]))
        return row, image, str(image_file), directory

    def audit_baseline(self, row, image, simv):
        checked = ev.Evidence()
        checked.baseline_row(row, image, simv)
        return checked

    def repin_row(self, row, directory, path):
        row['files'].update(full.pins([path]))
        self.write(directory / 'outcomes/old.json', row)

    def test_baseline_native_directed_random_replay(self):
        for kind in ('directed', 'random', 'replay'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                row, image, simv, _ = self.baseline(kind)
                self.audit_baseline(row, image, simv)

    def test_baseline_row_files_cannot_be_missing_empty_or_stale(self):
        row, image, simv, _ = self.baseline()
        for files in ({}, {str(self.root / 'missing'): '0' * 64},
                      {p: '0' * 64 for p in row['files']}):
            with self.subTest(files=files), self.assertRaises(ValueError):
                self.audit_baseline(dict(row, files=files), image, simv)

    def test_baseline_wrong_elf_rejected_despite_pass_flags(self):
        row, image, simv, _ = self.baseline()
        row['elf_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'elf_sha256'):
            self.audit_baseline(row, image, simv)

    def test_baseline_rehashed_wrong_metadata_rejected(self):
        row, image, simv, directory = self.baseline()
        path = next(Path(p) for p in row['files'] if p.endswith('inputs.json'))
        value = full.read(path)
        value['simv']['image_sha256'] = {'different': '0' * 64}
        self.write(path, value)
        self.repin_row(row, directory, path)
        with self.assertRaisesRegex(ValueError, 'metadata image'):
            self.audit_baseline(row, image, simv)

    def test_baseline_independent_audit_policy_rechecked(self):
        row, image, simv, directory = self.baseline()
        path = next(Path(p) for p in row['files'] if p.endswith('independent_audit.json'))
        value = full.read(path)
        value['policy']['require_trace'] = False
        self.write(path, value)
        self.repin_row(row, directory, path)
        with self.assertRaisesRegex(RuntimeError, 'independent audit'):
            self.audit_baseline(row, image, simv)

    def test_baseline_audit_must_be_in_row_files(self):
        row, image, simv, directory = self.baseline()
        row['files'] = {p: h for p, h in row['files'].items() if not p.endswith('independent_audit.json')}
        self.write(directory / 'outcomes/old.json', row)
        with self.assertRaisesRegex(ValueError, 'does not bind'):
            self.audit_baseline(row, image, simv)

    def test_unknown_historical_type_fails_closed(self):
        row, image, simv, _ = self.baseline()
        with self.assertRaisesRegex(ValueError, 'unsupported historical'):
                self.audit_baseline(dict(row, kind='legacy'), image, simv)

    def uvm_baseline(self, kind):
        row, image, simv, directory = self.baseline()
        target = directory / 'results/old'
        plan = full.read(directory / 'plan.json')
        case = plan['cases'][0]
        case['kind'] = kind
        case['contract'] = full.contract(case)
        elf = self.write(target / 'work/input.elf', 'ELF')
        log = self.write(target / 'work/run.vcs.log', 'PASSED: test\n')
        trace = self.write(target / 'work/vector_trace.csv', 'trace\n')
        report = {'status': 'PASS', 'issues': [], 'elf_sha256': row['elf_sha256'],
                  'sim_image_sha256': image, 'reset_kind': None,
                  'log_sha256': full.base.sha256(log), 'vector_trace_sha256': full.base.sha256(trace)}
        primary = self.write(target / 'uvm_result.json', report)
        audit = self.write(target / 'independent_uvm_audit.json', report)
        vdb = target / 'code.vdb'
        vdb.mkdir()
        row.update(kind=kind, contract=case['contract'], vdb=str(vdb),
                   files=full.pins([elf, log, trace, primary, audit]), simulator_returncode=0)
        self.write(directory / 'outcomes/old.json', row)
        self.write(directory / 'plan.json', plan)
        self.write(directory / 'plan.sha256.json', full.pins([directory / 'plan.json']))
        return row, image, simv, directory

    def test_uvm_and_axpy_require_matching_independent_report(self):
        for kind in ('uvm', 'axpy'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                row, image, simv, directory = self.uvm_baseline(kind)
                self.audit_baseline(row, image, simv)
                audit = directory / 'results/old/independent_uvm_audit.json'
                report = full.read(audit)
                report['status'] = 'FAIL'
                self.write(audit, report)
                self.repin_row(row, directory, audit)
                with self.assertRaisesRegex(ValueError, 'independent UVM audit'):
                    self.audit_baseline(row, image, simv)

    def test_uvm_report_hash_must_bind_log_contents(self):
        row, image, simv, directory = self.uvm_baseline('uvm')
        log = directory / 'results/old/work/run.vcs.log'
        self.write(log, 'another run\n')
        self.repin_row(row, directory, log)
        with self.assertRaisesRegex(ValueError, 'evidence hash differs'):
            self.audit_baseline(row, image, simv)

    def test_legacy_unlisted_ledger_and_all_reports_pinned(self):
        row, image, _, directory = self.baseline()
        checked = ev.Evidence()
        self.assertEqual(checked.ledger(directory, image), [row])
        self.assertIn(str(directory / 'all-outcomes.json'), checked.files)
        for path in full.read(directory / 'collection.json')['reports']:
            self.assertIn(path, checked.files)
        self.write(directory / 'combined-dve/summary.csv', 'replaced summary')
        with self.assertRaises(Exception):
            full.check(checked.files)

    def precheck_fixture(self, fmt):
        stem = {'scalar-spike-v1': 'scalar_gap35_memory', 'csr-spike-v1': 'csr_gap35_permissions',
                'rvv-spike-v1': 'vgap35_mask_ta', 'accel-host-v1': 'qbs_gap35_descriptor'}[fmt]
        directory = self.root / fmt
        source = self.write(directory / (stem + '.c'), 'int main(void) {return 0;}')
        elf = self.write(directory / (stem + '.elf'), 'ELF')
        spike = self.write(directory / (stem + '.spike'), 'SPIKE ELF')
        tool = self.write(directory / 'spike', 'SPIKE tool')
        sources = full.pins([source])
        name = ('app:' if fmt == 'accel-host-v1' else 'rvv:') + stem
        record = {'test': name, 'elf': str(elf), 'elf_sha256': full.base.sha256(elf),
                  'returncode': 0, 'status': 'PASS', 'command': [str(tool), '--isa=rv64gcv', str(spike)],
                  'spike_elf': str(spike), 'spike_sha256': full.base.sha256(spike)}
        log = self.write(directory / (stem + '.spike.log'), f'{stem} checks=3 failures=0\nPASSED: {stem}\n')
        record['spike_log'] = str(log)
        schema = {'format': fmt}
        extra = []
        if fmt == 'scalar-spike-v1':
            record['status'] = 'SPIKE_PASS_RTL_NOT_RUN'
        elif fmt == 'rvv-spike-v1':
            record.update(binary=str(elf), binary_sha256=full.base.sha256(elf),
                          spike_binary=str(spike), source_hashes=sources, log=str(log),
                          spike_tool_sha256=full.base.sha256(tool))
            self.write(log, f'gap35 checks=3 failures=0\nPASSED: {source}!\n')
        elif fmt == 'csr-spike-v1':
            validator = full.ROOT / 'verification/tests/build_gap35_csr.py'
            sources.update(full.pins([validator]))
            spec = importlib.util.spec_from_file_location('fixture_csr', validator)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            lines = []
            for phase in range(132):
                legal = phase < 6
                lines.append(f'PROBE phase={phase} priv=3 insn=340026f3 legal={int(legal)} '
                             f'cause={11 if legal else 2:x} epc={0x80000004 if legal else 0x80000000:x} '
                             f'tval={0 if legal else 0x340026f3:x} rd=1122334455667788')
            lines += [f'{stem} phases=132 checks=1056 illegal=126 legal=6 failures=0', 'PASSED: ' + stem]
            self.write(log, '\n'.join(lines) + '\n')
            record.update(module.validate_log(stem, log.read_text()))
            record['spike_elf_sha256'] = full.base.sha256(spike)
            schema['log'] = str(log)
        else:
            message = f'PASSED: {stem} checks=4 errors=0'
            self.write(log, message + '\n')
            record = {'name': stem, 'binary': str(elf), 'binary_sha256': full.base.sha256(elf),
                      'sources': list(sources), 'source_hashes': sources, 'host_reference': str(source),
                      'host_log': str(log), 'host_result': message,
                      'custom_instruction_execution_prechecked': False, 'vcs_launched': False}
        if fmt in ('scalar-spike-v1', 'csr-spike-v1'):
            hashes = self.write(directory / 'source_hashes.json', sources)
            schema['source_hashes'] = str(hashes)
            extra.append(str(hashes))
        path = self.write(directory / 'record.json',
                          [record] if fmt in ('scalar-spike-v1', 'rvv-spike-v1') else record)
        schema['record'] = str(path)
        return {'name': name, 'binary': str(elf), 'sources': list(sources),
                'source_audit': 'Independent oracle', 'evidence': [str(path), str(log), *extra],
                'precheck': schema}

    def test_all_four_native_precheck_formats(self):
        for fmt in ('scalar-spike-v1', 'csr-spike-v1', 'rvv-spike-v1', 'accel-host-v1'):
            with self.subTest(fmt=fmt):
                item = self.precheck_fixture(fmt)
                result = ev.precheck(item, ev.Evidence())
                self.assertEqual(result['status'], 'PASS')
                self.assertEqual(result['precheck']['format'], fmt)
                self.assertEqual(result['scope'], 'host-reference-only' if fmt == 'accel-host-v1' else 'Spike-only')

    def test_precheck_fail_log_source_and_elf_drift_rejected(self):
        for change in ('log', 'source', 'elf', 'status', 'returncode', 'spike'):
            with self.subTest(change=change):
                item = self.precheck_fixture('rvv-spike-v1')
                record_path = Path(item['precheck']['record'])
                records = full.read(record_path)
                if change in ('status', 'returncode'):
                    records[0][change] = 'FAIL' if change == 'status' else 1
                    self.write(record_path, records)
                else:
                    path = {'log': item['evidence'][1], 'source': item['sources'][0],
                            'elf': item['binary'], 'spike': records[0]['spike_binary']}[change]
                    self.write(Path(path), 'FAIL: altered evidence\n')
                with self.assertRaises(ValueError):
                    ev.precheck(item, ev.Evidence())

    def test_precheck_unknown_format_and_unbound_compile_source(self):
        item = self.precheck_fixture('rvv-spike-v1')
        item['precheck']['format'] = 'unknown'
        with self.assertRaisesRegex(ValueError, 'unsupported precheck'):
            ev.precheck(item, ev.Evidence())
        item['precheck']['format'] = 'rvv-spike-v1'
        item['sources'].append(str(self.write(self.root / 'unbound.h', 'changed')))
        with self.assertRaisesRegex(ValueError, 'compile sources'):
            ev.precheck(item, ev.Evidence())

    def test_prepare_rewrites_plan_pins_and_sha(self):
        output = self.root / 'prepared'
        report = self.write(self.root / 'summary.csv', 'baseline')
        checked = ev.Evidence()
        checked.pin(report)
        cases = [{'name': 'rvv:new', 'elf_sha256': 'a' * 64}]
        def old_prepare(out, selection):
            self.write(out / 'inputs/baseline-ledger.json', [])
            self.write(out / 'plan.json', {'files': {}, 'cases': [
                {'source_name': 'rvv:new', 'elf_sha256': 'a' * 64}]})
        with patch.object(ev, 'validate', return_value=(checked, [], cases)), \
                patch.object(run.base, 'prepare', side_effect=old_prepare), \
                patch.object(run, 'frozen') as frozen:
            run.prepare(output, self.root / 'selection.json')
        plan = full.read(output / 'plan.json')
        self.assertEqual(plan['checked_extension'], run.VERSION)
        self.assertEqual(plan['files'][str(report)], checked.files[str(report)])
        full.check(full.read(output / 'plan.sha256.json'))
        full.check(plan['files'])
        frozen.assert_called_once_with(output, all_cases=True)
        self.assertFalse(full.read(output / 'checked-preflight.json')['simulations_started'])

    def test_prepare_failure_does_not_call_old_runner(self):
        output = self.root / 'failed'
        with patch.object(ev, 'validate', side_effect=ValueError('stale evidence')), \
                patch.object(run.base, 'prepare') as old_prepare:
            with self.assertRaisesRegex(ValueError, 'stale evidence'):
                run.prepare(output, self.root / 'selection.json')
        old_prepare.assert_not_called()
        self.assertFalse(full.read(output / 'checkpoint.json')['simulations_started'])
        self.assertFalse(full.read(output / 'checked-failure.json')['launch_attempted'])

    def test_drift_after_old_prepare_revokes_launch(self):
        output = self.root / 'raced'
        report = self.write(self.root / 'summary.csv', 'baseline')
        checked = ev.Evidence()
        checked.pin(report)
        def old_prepare(out, selection):
            self.write(out / 'inputs/baseline-ledger.json', [])
            self.write(out / 'plan.json', {'files': {}, 'cases': []})
            self.write(out / 'checkpoint.json', {'status': 'PREPARED', 'simulations_started': False})
            self.write(report, 'changed during prepare')
        with patch.object(ev, 'validate', return_value=(checked, [], [])), \
                patch.object(run.base, 'prepare', side_effect=old_prepare):
            with self.assertRaises(Exception):
                run.prepare(output, self.root / 'selection.json')
        self.assertNotIn('checked_extension', full.read(output / 'plan.json'))
        self.assertEqual(full.read(output / 'checkpoint.json')['status'], 'PREFLIGHT_FAILED')
        self.assertFalse(full.read(output / 'checked-failure.json')['launch_attempted'])

    def test_worker_dispatch_uses_new_adapter(self):
        with patch.object(full.batch, 'SCRIPT'), patch.object(full.batch, 'frozen'), \
                patch.object(full.batch, 'commands'), patch.object(full.batch, 'summarize'), \
                patch.object(full.batch, 'schedule'):
            run.install_hooks()
            self.assertEqual(full.batch.SCRIPT, run.SCRIPT)
            self.assertIs(full.batch.frozen, run.frozen)
            self.assertIs(full.batch.summarize, run.summarize)
            self.assertIs(full.batch.schedule, full.original_schedule)

    def test_csv_drift_blocks_launch_and_records_failure(self):
        output = self.root / 'launch'
        report = self.write(self.root / 'summary.csv', 'baseline')
        plan = {'checked_extension': run.VERSION, 'files': full.pins([report])}
        self.write(output / 'plan.json', plan)
        self.write(report, 'corrupted summary')
        def check_files(out, case=None, all_cases=False):
            self.assertTrue(all_cases)
            full.check(plan['files'])
            return plan
        with patch.object(full, 'frozen', side_effect=check_files), \
                patch.object(run.subprocess, 'call') as call:
            with self.assertRaises(Exception):
                run.launch(output)
        call.assert_not_called()
        self.assertEqual(full.read(output / 'checked-failure.json')['phase'], 'checked launch')
        self.assertFalse(full.read(output / 'checkpoint.json')['simulations_started'])

    def test_plan_without_checked_marker_cannot_launch(self):
        with patch.object(full, 'frozen', return_value={}), patch.object(run.subprocess, 'call') as call:
            with self.assertRaisesRegex(ValueError, 'lacks checked admission'):
                run.launch(self.root / 'unchecked')
        call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
