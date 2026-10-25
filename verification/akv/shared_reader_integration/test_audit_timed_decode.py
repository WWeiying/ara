"""Independent synthetic schemas/receipts. No real jobs, builds or simulation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import audit_timed_decode as a


def fixture():
    records, trials, timings = [], [], []
    start = 100
    for index, count in enumerate((197,84,197,774,373,774,137,137,137,386,98,386)):
        case, trial = divmod(index, 3)
        group = []
        for _ in range(count):
            row = dict.fromkeys(a.s.PERF_FIELDS, 0)
            row.update(seq=len(records)+1, busy_cycles=10, success=1, command=6)
            group.append(row)
            records.append(row)
        totals = a.s.totals(group)
        cycles = count*10+1000
        trials.append(dict(case=case, trial=trial, requested=int(trial == 1), checksum='0123456789abcdef',
                           fcsr=3, vcsr=5, hardware_totals=totals, cycles=cycles))
        timings.append(dict(case=case, trial=trial, start=start, end=start+cycles,
                            cycles=cycles, command_busy_cycles=count*10))
        start += cycles+1000
    return dict(state='PASS', complete_native_call_cycles=True, trials=trials, timings=timings,
                hardware_records=records, raw_hardware_summary=a.s.totals(records),
                scope='Synthetic schema only; not hardware evidence', ggml_deployed=False)


def set_cycles(raw, index, cycles):
    raw['trials'][index]['cycles'] = cycles
    raw['timings'][index].update(cycles=cycles, end=raw['timings'][index]['start']+cycles)


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.old = fixture()

    def test_exact(self):
        result = a.compare_pair(self.old, copy.deepcopy(self.old))
        self.assertTrue(result['resource_regression_gate_pass'])
        self.assertTrue(result['complete_operator_performance_accepted'])
        self.assertEqual(result['command_comparison']['commands'], 3680)

    def test_slower_call_cannot_hide_in_faster_sum(self):
        new = copy.deepcopy(self.old)
        set_cycles(new, 0, new['trials'][0]['cycles']+1)
        set_cycles(new, 1, new['trials'][1]['cycles']-100)
        result = a.compare_pair(self.old, new)
        self.assertFalse(result['resource_regression_gate_pass'])
        self.assertFalse(result['complete_operator_performance_accepted'])

    def test_offsetting_commands_reject_same_cycles_same_totals(self):
        new = copy.deepcopy(self.old)
        new['hardware_records'][0]['busy_cycles'] += 1
        new['hardware_records'][1]['busy_cycles'] -= 1
        result = a.compare_pair(self.old, new)
        self.assertTrue(result['per_call_counter_equivalence'])
        self.assertFalse(result['resource_regression_gate_pass'])
        self.assertFalse(result['complete_operator_performance_accepted'])
        self.assertEqual(result['command_comparison']['changed_commands'], 2)

    def test_missing_extra_schema_order_records(self):
        changes = [lambda r: r['hardware_records'].pop(),
                   lambda r: r['hardware_records'].append(copy.deepcopy(r['hardware_records'][0])),
                   lambda r: r['hardware_records'][0].update(unexpected=0),
                   lambda r: r['hardware_records'][0].update(seq=2),
                   lambda r: r['hardware_records'][0].update(busy_cycles=True),
                   lambda r: r['trials'].pop(),
                   lambda r: r['trials'][0].update(case=1),
                   lambda r: r['trials'][0].update(extra=0)]
        for change in changes:
            new = copy.deepcopy(self.old)
            change(new)
            with self.subTest(change=change), self.assertRaises(ValueError):
                a.compare_pair(self.old, new)

    def test_missing_bad_cycles_and_timing(self):
        changes = [lambda r: r['trials'][0].pop('cycles'),
                   lambda r: r['trials'][0].update(cycles=True),
                   lambda r: r['timings'][0].update(end=100),
                   lambda r: r['timings'][0].update(command_busy_cycles=1),
                   lambda r: r['timings'][1].update(start=1),
                   lambda r: set_cycles(r, 0, 1)]
        for change in changes:
            new = copy.deepcopy(self.old)
            change(new)
            with self.assertRaises(ValueError):
                a.compare_pair(self.old, new)

    def test_numeric_difference_rejected(self):
        for field, value in (('checksum','0000000000000000'), ('fcsr',1), ('vcsr',0)):
            new = copy.deepcopy(self.old)
            new['trials'][0][field] = value
            with self.assertRaises(ValueError):
                a.compare_pair(self.old, new)

    def test_unique_imports_and_resource_labels(self):
        self.assertEqual(a.builder.__name__, '_timed_audit_build')
        self.assertEqual(a.worker.__name__, '_timed_audit_runner')
        self.assertIs(a.worker.checked_build, a.builder.checked_build)
        self.assertIs(a.worker.check_log, a.checker.check_log)
        self.assertFalse(a.LABELS['ordinary_rvv_comparison'])
        self.assertFalse(a.LABELS['acceleration_against_rvv'])
        self.assertIn('dual-reader', a.LABELS['baseline'])


class TerminalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root/'run'
        self.work = self.run/'work'
        self.work.mkdir(parents=True)
        self.build = self.root/'build'
        self.build.mkdir()
        self.elf = self.build/'timed.elf'
        self.elf.write_bytes(b'synthetic ELF, never executed')
        self.simv = self.root/'image/simv'
        self.simv.parent.mkdir()
        self.simv.write_bytes(b'synthetic image, never executed')
        self.raw = fixture()
        self.image = a.s.hashes([self.simv])
        self.identity = dict(variant='baseline', accepted_gate='synthetic-old-acceptance')
        self.build_pins = a.s.hashes([self.elf])
        self.build_report = dict(elf=str(self.elf), elf_sha256=a.s.digest(self.elf), simv=str(self.simv))
        self.saved = {**self.build_pins, **self.image,
                      **a.s.hashes([Path(sys.executable).resolve(), *[a.TIMED/name for name in
                         ('timed_spec.py','build.py','timed_check.py','run.py')]])}
        self.write(self.work/'run.vcs.log', 'synthetic transcript; frozen checker is mocked for identity tests\n')
        self.write(self.work/'vector_trace.csv', 'synthetic trace\n')
        self.write(self.work/'uvm_result.json', dict(log_sha256=a.s.digest(self.work/'run.vcs.log'),
                                                   vector_trace_sha256=a.s.digest(self.work/'vector_trace.csv')))
        for name in ('manifest-before.log','manifest-after.log','image-contract.log'):
            self.write(self.run/name, 'synthetic pre/post proof\n')
        self.write(self.run/'source-pins.json', self.saved)
        self.make_commands()
        self.status = dict(state='PASS', child_pid=None, kind='timed_decode', variant='baseline',
            build=str(self.build), image_identity=self.identity, simv=str(self.simv), elf=str(self.elf), timeout_seconds=10800,
            **{key:0 for key in ('running_exit_code','checking_exit_code','manifest-before_exit_code',
                                'manifest-after_exit_code','image_contract_exit_code')})
        evidence = a.s.hashes([self.work/name for name in ('run.vcs.log','vector_trace.csv','uvm_result.json',
                                                        'console.command.json','checker.command.json')])
        evidence.update(a.s.hashes([self.run/name for name in ('source-pins.json','manifest-before.log',
                                                            'manifest-after.log','image-contract.log')]))
        self.report = dict(copy.deepcopy(self.raw), kind='timed_decode', image_identity=self.identity,
            simulator_exit_code=0, post_pins_match=True, independent_protocol_checked=True,
            model_execution=False, production_promoted=False, complete_operator_performance_accepted=False,
            source_pins_sha256=a.s.digest(self.run/'source-pins.json'), elf_sha256=a.s.digest(self.elf),
            evidence_sha256=evidence)
        for target, kwargs in (
            ('checked_build', dict(return_value=(self.build_report, self.image, self.build_pins))),):
            patcher = mock.patch.object(a.builder, target, **kwargs)
            patcher.start(); self.addCleanup(patcher.stop)
        for obj, name, kwargs in (
            (a.worker, 'select_image', dict(return_value=(self.simv, self.image, self.image, self.identity))),
            (a.s, 'image_files', dict(return_value=[self.simv])),
            (a.s, 'check_result', dict(return_value=None)),
            (a.checker, 'check_log', dict(side_effect=lambda _: copy.deepcopy(self.raw))),
            (a, 'check_manifests', dict(return_value=None))):
            patcher = mock.patch.object(obj, name, **kwargs)
            patcher.start(); self.addCleanup(patcher.stop)

    @staticmethod
    def write(path, data):
        path.write_text(data if isinstance(data, str) else json.dumps(data))

    def make_commands(self):
        log, trace, protocol = (self.work/name for name in ('run.vcs.log','vector_trace.csv','uvm_result.json'))
        commands = {
            self.work/'console.command.json': ([self.simv,'-no_save','-l',log,'+PRELOAD='+str(self.elf),
                '+TESTCASE=akv_timed_decode_baseline','+NO_FSDB','+NO_INSTR_TRACE','+AKV_PERF','+AKV_SUMMARY',
                '+VECTOR_TRACE='+str(trace),'+ARA_CONTRACT_TRACE_LIMIT=2000000','+ARA_UVM_TRACE_LIMIT=2000000'],10800),
            self.work/'checker.command.json': ([sys.executable,'-B','-m','ara_verify.uvm_dut','--require-events',
                '--require-backend','--require-axi','--require-axi-write','--vector-trace',trace,'--log',log,
                '--simv',self.simv,'--elf',self.elf,'--output',protocol],600),
            self.run/'image-contract.command.json': (['bash',a.ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                self.simv.parent,self.elf,'akv_v2'],180)}
        for path, (argv, timeout) in commands.items():
            self.write(path, dict(argv=list(map(str, argv)), cwd=str(path.parent), timeout_seconds=timeout))

    def terminal(self):
        self.write(self.run/'status.json', self.status)
        self.write(self.run/'result.json', self.report)
        return a.terminal(self.run, 'baseline', {})

    def test_terminal_identity_path(self):
        record = self.terminal()
        self.assertEqual(record['raw']['trials'], self.raw['trials'])
        self.assertEqual(record['image_identity'], self.identity)

    def test_running_failed_phase_wrong_kind_reject(self):
        initial = copy.deepcopy(self.status)
        for key, value in (('state','RUNNING'), ('child_pid',123), ('kind','decode'),
                           ('variant','unified'), ('checking_exit_code',False), ('running_exit_code',1)):
            self.status = dict(initial, **{key:value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.terminal()

    def test_wrong_baseline_image_and_elf_reject(self):
        initial = copy.deepcopy(self.status)
        for key, value in (('simv','/unified/image'), ('elf','/different/elf'),
                           ('image_identity',dict(variant='unified'))):
            self.status = dict(initial, **{key:value})
            with self.assertRaises(ValueError):
                self.terminal()

    def test_report_not_raw_and_missing_evidence_reject(self):
        original = copy.deepcopy(self.report)
        self.report['trials'][0]['cycles'] += 1
        with self.assertRaises(ValueError):
            self.terminal()
        self.report = original
        self.report['evidence_sha256'].pop(str(self.work/'vector_trace.csv'))
        with self.assertRaises(ValueError):
            self.terminal()

    def test_wrong_actual_checker_flags_even_rehashed_reject(self):
        path = self.work/'checker.command.json'
        command = json.loads(path.read_text())
        command['argv'].remove('--require-axi-write')
        self.write(path, command)
        self.report['evidence_sha256'][str(path)] = a.s.digest(path)
        with self.assertRaises(ValueError):
            self.terminal()

    def test_uvm_trace_identity_even_rehashed_reject(self):
        path = self.work/'uvm_result.json'
        proof = json.loads(path.read_text())
        proof['vector_trace_sha256'] = '0'*64
        self.write(path, proof)
        self.report['evidence_sha256'][str(path)] = a.s.digest(path)
        with self.assertRaises(ValueError):
            self.terminal()

    def test_source_drift_and_post_drift_reject(self):
        record = self.terminal()
        self.elf.write_bytes(b'changed')
        with self.assertRaises((ValueError, RuntimeError)):
            a.s.verify_pins(record['pins'])
        with self.assertRaises((ValueError, RuntimeError)):
            self.terminal()


class AuditStateTests(unittest.TestCase):
    def test_receipt_regression_not_pass_and_full_raw_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, unified = root/'old', root/'new'
            baseline.mkdir(); unified.mkdir()
            raw_old, raw_new = fixture(), fixture()
            set_cycles(raw_new, 0, raw_new['trials'][0]['cycles']+1)
            def record(raw):
                return dict(run=str(root), build='/same/build', elf='/same/elf', elf_sha256='hash', raw=raw,
                            pins={}, simv='/synthetic/image', image={})
            with mock.patch.object(a, 'helper_pins', return_value={'synthetic':'hash'}), \
                 mock.patch.object(a, 'terminal', side_effect=[record(raw_old), record(raw_new)]), \
                 mock.patch.object(a, 'check_manifests'), \
                 mock.patch.object(a.s, 'verify_pins'), mock.patch.object(a.s, 'image_files', return_value=[]), \
                 mock.patch.object(a.s, 'hashes', return_value={}):
                result = a.audit(baseline, unified)
            self.assertEqual(result['state'], 'REGRESSION')
            self.assertFalse(result['complete_operator_performance_accepted'])
            self.assertEqual(len(result['baseline']['raw']['hardware_records']), 3680)
            self.assertEqual(result['unified']['raw'], raw_new)

    def test_same_elf_and_build_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old, new = root/'old', root/'new'
            old.mkdir(); new.mkdir()
            before = dict(build='/one/build', elf='/one/elf', elf_sha256='hash')
            for key, value in (('build','/two/build'), ('elf','/two/elf'), ('elf_sha256','different')):
                after = dict(before, **{key:value})
                with mock.patch.object(a, 'helper_pins', return_value={}), \
                     mock.patch.object(a, 'terminal', side_effect=[before, after]), \
                     mock.patch.object(a.s, 'verify_pins'), self.assertRaises(ValueError):
                    a.audit(old, new)

    def test_manifest_inventory_and_saved_prepost_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simv, source = root/'simv', root/'unit.sv'
            simv.write_text('not executed')
            source.write_text('synthetic source')
            rows = [dict(path=str(source), sha256=a.s.digest(source))]
            manifest = dict(schema_version=1, files=rows, filelist=str(root/'sources.f'),
                            repo_root=str(root), extra_sources=[])
            (root/'vcs_source_manifest.json').write_text(json.dumps(manifest))
            pins = a.s.hashes([source, Path(sys.executable).resolve()])
            for stage in ('manifest-before', 'manifest-after'):
                (root/(stage+'.log')).write_text(json.dumps(dict(status='PASS', file_count=1, changed=[])))
                (root/(stage+'.command.json')).write_text(json.dumps(dict(
                    argv=[sys.executable,'-B','-m','ara_verify.vcs_source_manifest','--output',
                          str(root/'vcs_source_manifest.json'),'--check'], cwd=str(root), timeout_seconds=300)))
            with mock.patch.object(a.inventory, 'collect', return_value=rows):
                a.check_manifests(root, simv, dict(pins))
            with mock.patch.object(a.inventory, 'collect', return_value=rows+[
                    dict(path='/new/header.svh', sha256='new')]), self.assertRaises(ValueError):
                a.check_manifests(root, simv, dict(pins))
            (root/'manifest-after.log').write_text(json.dumps(dict(status='PASS', file_count=2, changed=[])))
            with mock.patch.object(a.inventory, 'collect', return_value=rows), self.assertRaises(ValueError):
                a.check_manifests(root, simv, dict(pins))


if __name__ == '__main__':
    unittest.main()
