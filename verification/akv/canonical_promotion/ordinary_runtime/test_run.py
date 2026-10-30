"""Mocked source/image receipts and execution; no fake RTL result is published."""
import argparse
import copy
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import run as w
from threeway_run_test import fixture


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root, self.build = self.base / 'root', self.base / 'build'
        self.root.mkdir(); self.build.mkdir()
        self.files = {}
        def put(path, text='fixture'):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            return path
        self.put = put
        self.sim = self.build / 'sim'
        self.image_files = [put(self.sim / n) for n in ('simv', 'simulator.conf', 'vcs_source_manifest.json', 'simv.daidir/a.so')]
        self.old_list = put(self.root / 'old-list.f')
        self.filelist = put(self.build / 'hardware-build/vcs/bender_script_default')
        self.expected = put(self.build / 'expected-sources.f')
        self.dpi = put(self.build / 'hardware-build/work-dpi/elfloader.o')
        put(self.build / 'hardware-build/work-dpi/ara_dpi.so')
        self.uvm = [put(self.root / ('uvm/' + str(i) + '.sv')) for i in range(4)]
        self.source = put(self.root / 'hardware/src/source.sv')
        self.lock = put(self.root / 'Bender.lock')
        self.helper = put(self.root / 'required-helper.py')
        self.vcs = put(self.root / 'tools/vcs')
        put(self.sim / 'comp.vcs.log')
        put(self.build / 'make.log')
        w.s.atomic_json(self.build / 'planned-command.json', ['make', 'compile'])
        w.s.atomic_json(self.build / 'make.command.json', dict(argv=['make', 'compile']))
        self.graph_paths = [self.source, self.lock, *self.uvm]
        def collect(filelist, root, extras):
            return [dict(path=str(p), sha256=w.s.digest(p)) for p in [filelist, *self.graph_paths, *[p for p in extras if p not in self.graph_paths]]]
        self.collect = collect
        self.manifest = dict(schema_version=1, repo_root=str(self.root), filelist=str(self.filelist),
            extra_sources=list(map(str, [self.dpi, *self.uvm])),
            files=collect(self.filelist, self.root, [self.dpi, *self.uvm]))
        w.s.atomic_json(self.sim / 'vcs_source_manifest.json', self.manifest)
        image = w.s.hashes(self.image_files)
        w.s.atomic_json(self.build / 'image-pins.json', image)
        self.pins = w.s.hashes([self.expected, *self.graph_paths, self.vcs, self.helper])
        self.report = dict(state=w.STATE, schema='canonical_soc_v1', canonical=True, source_root=str(self.root),
            plan_sha256=w.builder.PLAN_SHA, post_pins_match=True, compiler_exit_code=0,
            execution='NOT_RUN', simulations_launched=0, performance_measured=False,
            simv=str(self.sim / 'simv'), image_pins=image, config={'test':'config'},
            lint={'command_argv':[str(self.vcs)]})
        self.status = dict(state=w.STATE, child_pid=None, canonical=True, source_root=str(self.root),
                           execution='NOT_RUN', compile_exit_code=0)
        self.common = SimpleNamespace(latency=SimpleNamespace(tools=SimpleNamespace(collect=collect)),
            SOC_REPEAT_HASHES={}, check_soc_compile=lambda *args: self.report['lint'])
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        replacements = [(w, 'ROOT', self.root), (w.builder, 'guard', lambda: {'files':[
            dict(target='hardware/src/source.sv', after_sha256=self.pins[str(self.source)])]}),
            (w.builder, 'LOCKED', {'Bender.lock':w.s.digest(self.lock)}),
            (w.builder, 'OLD_LIST', self.old_list), (w.builder, 'OLD_LIST_SHA', w.s.digest(self.old_list)),
            (w.builder, 'UVM', self.uvm), (w.builder, 'load_common', lambda:self.common),
            (w.builder, 'expected_graph', lambda text:['fixture']),
            (w.builder, 'check_graph', lambda *args:None), (w.builder, 'check_config', lambda path:{'test':'config'}),
            (w, 'build_dependencies', lambda common:[self.helper]),
            (w.s, 'image_files', lambda simv:self.image_files)]
        for obj, name, value in replacements: self.stack.enter_context(patch.object(obj, name, value))
        self.seal()

    def seal(self):
        w.s.atomic_json(self.build / 'source-pins.json', self.pins)
        self.report['source_pins_sha256'] = w.s.digest(self.build / 'source-pins.json')
        paths = [self.build / n for n in ('source-pins.json', 'image-pins.json', 'planned-command.json',
                 'make.log', 'make.command.json', 'hardware-build/work-dpi/ara_dpi.so')]
        paths += [self.filelist, self.dpi, self.sim / 'comp.vcs.log', *self.image_files]
        self.report['artifact_pins'] = w.s.hashes(paths)
        w.s.atomic_json(self.build / 'result.json', self.report)
        w.s.atomic_json(self.build / 'status.json', self.status)
        self.sha = w.s.digest(self.build / 'result.json')

    def checked(self):
        return w.checked_soc(self.build, self.sha)

    def test_valid_typed_receipt_returns_full_pins(self):
        report, pins, image = self.checked()
        self.assertEqual(report['schema'], 'canonical_soc_v1')
        self.assertEqual(image, self.report['image_pins'])
        self.assertIn(str(self.build / 'result.json'), pins)
        w.s.verify_pins(pins)

    def test_state_schema_bool_and_old_overlay_reject(self):
        original = dict(self.report)
        for key, value in [('state','SOC_BUILT_NOT_EXECUTED'), ('schema','overlay'), ('canonical',1),
                           ('post_pins_match',1), ('compiler_exit_code',False), ('simulations_launched',False)]:
            self.report = dict(original, **{key:value}); self.seal()
            with self.subTest(key=key), self.assertRaises(ValueError): self.checked()

    def test_nonterminal_or_wrong_exit_reject(self):
        for key, value in [('child_pid',42), ('compile_exit_code',1), ('compile_exit_code',False)]:
            before = dict(self.status); self.status[key] = value; self.seal()
            with self.assertRaises(ValueError): self.checked()
            self.status = before

    def test_reviewed_sha_and_source_receipt_reject(self):
        with self.assertRaises(ValueError): w.checked_soc(self.build, '0'*64)
        self.put(self.build / 'source-pins.json', '{}')
        with self.assertRaises(ValueError): self.checked()

    def test_complete_artifact_and_helper_pins_required(self):
        path = str(self.sim / 'comp.vcs.log')
        self.report['artifact_pins'].pop(path)
        w.s.atomic_json(self.build / 'result.json', self.report)
        self.sha = w.s.digest(self.build / 'result.json')
        with self.assertRaisesRegex(ValueError, 'artifact'): self.checked()
        self.pins.pop(str(self.helper)); self.seal()
        with self.assertRaisesRegex(ValueError, 'helper/tool'): self.checked()

    def test_source_dependency_and_image_drift_reject(self):
        self.pins.pop(str(self.uvm[0])); self.seal()
        with self.assertRaisesRegex(ValueError, 'source pins'): self.checked()
        self.pins[str(self.uvm[0])] = w.s.digest(self.uvm[0]); self.seal()
        self.put(self.sim / 'simv.daidir/a.so', 'drift')
        with self.assertRaisesRegex(ValueError, 'image inventory'): self.checked()

    def test_snapshot_manifest_or_wrong_uvm_reject_even_if_resealed(self):
        for key, value in [('repo_root',str(self.root / 'snapshot')), ('extra_sources',[str(self.dpi)])]:
            bad = dict(self.manifest, **{key:value})
            w.s.atomic_json(self.sim / 'vcs_source_manifest.json', bad)
            self.report['image_pins'] = w.s.hashes(self.image_files)
            w.s.atomic_json(self.build / 'image-pins.json', self.report['image_pins'])
            self.seal()
            with self.assertRaisesRegex(ValueError, 'actual canonical root'): self.checked()

    def test_promotion_guard_runs_before_receipt_consumer(self):
        with patch.object(w.builder, 'guard', side_effect=ValueError('not promoted')):
            with self.assertRaisesRegex(ValueError, 'not promoted'): self.checked()


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = fixture()
        cls.parsed = w.contract.original.check_log(text)
        cls.records = [w.s.numeric_fields(line[len('[AKV_PERF] '):], w.s.PERF_FIELDS)
                       for line in text.splitlines() if line.startswith('[AKV_PERF] ')]

    def exercise(self, directory, preflight=False, regression=False, failure=None, record_drift=False):
        build = directory / 'soc'; build.mkdir()
        output = directory / 'out'
        args = argparse.Namespace(soc_build=build, expected_soc_sha256='a'*64, output=output,
                                  timeout=10800, preflight_only=preflight)
        soc = dict(simv=str(build / 'sim/simv'))
        report = dict(elf=str(directory / 'frozen.elf'), elf_sha256='b'*64)
        new = copy.deepcopy(self.parsed)
        records = copy.deepcopy(self.records)
        if regression:
            new['trials'][0]['cycles'] += 1
            new['trials'][1]['cycles'] -= 1
        if record_drift:
            records[0]['busy_cycles'] += 1; records[1]['busy_cycles'] -= 1
        calls = []
        def execute(owner, argv, log, timeout, phase):
            calls.append((phase, list(map(str, argv))))
            if phase == 'RUNNING' and failure is not None: raise failure
            log.write_text('mock closed phase output')
            w.s.atomic_json(log.with_suffix('.command.json'), dict(argv=list(map(str,argv))))
            owner.state[phase.lower()+'_exit_code'] = 0
            if phase == 'RUNNING':
                for name in ('run.vcs.log','vector_trace.csv','commit_trace.csv'):
                    (output / 'work' / name).write_text('mock closed raw')
            if phase == 'CHECKING': (output / 'work/uvm_result.json').write_text('mock proof')
        with patch.object(w, 'checked_soc', return_value=(soc, {}, {})), \
             patch.object(w.baseline, 'Consumer') as consumer, \
             patch.object(w, 'own_pins', return_value={}), patch.object(w, 'verify_current'), \
             patch.object(w.Execution, 'execute', new=execute), \
             patch.object(w.contract, 'raw', return_value=(new, records)), \
             patch.object(w.contract, 'protocol') as protocol:
            consumer.return_value.checked_baseline.return_value = (report, self.parsed, self.records, {})
            if failure is not None or record_drift:
                with self.assertRaises(Exception): w.run(args)
                result = w.s.read_json(output / 'result.json')
            else:
                result = w.run(args)
            if not preflight and failure is None:
                protocol.assert_called_once_with(output, report['elf_sha256'], {})
        return result, calls, output

    def test_preflight_no_process_or_simulation(self):
        with tempfile.TemporaryDirectory() as d:
            result, calls, _ = self.exercise(Path(d), preflight=True)
        self.assertEqual(calls, [])
        self.assertEqual(result['state'], 'CANONICAL_ORDINARY_PREFLIGHT_NOT_RUN')
        self.assertEqual(result['simulations_launched'], 0)
        self.assertNotIn('simulator_exit_code', result)

    def test_real_finalization_code_pass_and_per_call_regression(self):
        for regression in (False, True):
            with self.subTest(regression=regression), tempfile.TemporaryDirectory() as d:
                result, calls, output = self.exercise(Path(d), regression=regression)
                self.assertEqual(result['state'], 'FAIL' if regression else 'PASS')
                self.assertEqual(result['comparison']['functional_same_work_pass'], True)
                self.assertEqual(result['comparison']['hardware_records_equal'], 3864)
                self.assertEqual([phase for phase,_ in calls],
                    ['MANIFEST_BEFORE','IMAGE_CONTRACT','RUNNING','CHECKING','MANIFEST_AFTER'])
                self.assertEqual([p for p,_ in calls].count('RUNNING'), 1)
                sim = next(argv for phase,argv in calls if phase == 'RUNNING')
                self.assertEqual(sim, list(map(str,w.old_run.simulation_command(
                    Path(d)/'soc/sim/simv',Path(d)/'frozen.elf',output/'work'))))
                for flag in ('--require-events','--require-backend','--require-axi','--require-axi-write'):
                    self.assertIn(flag, next(argv for phase,argv in calls if phase == 'CHECKING'))
                w.s.verify_pins(result['evidence_sha256'])
                self.assertIn(str(output/'work/commit_trace.csv'), result['evidence_sha256'])
                self.assertEqual(w.s.read_json(output/'status.json')['state'], result['state'])
                self.assertIsNone(w.s.read_json(output/'status.json')['child_pid'])

    def test_offsetting_hardware_drift_cannot_pass(self):
        with tempfile.TemporaryDirectory() as d:
            result, _, _ = self.exercise(Path(d), record_drift=True)
        self.assertEqual(result['state'], 'FAIL')
        self.assertIn('Per-command', result['error'])

    def test_timeout_failure_and_interrupt_never_pass(self):
        errors = [(w.subprocess.TimeoutExpired('simv', 10), 'TIMEOUT'),
                  (InterruptedError('stop'), 'INTERRUPTED'), (ValueError('nonzero simulator'), 'FAIL')]
        for error, state in errors:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as d:
                result, calls, output = self.exercise(Path(d), failure=error)
                self.assertEqual(result['state'], state)
                self.assertNotIn('CHECKING', [p for p,_ in calls])
                self.assertEqual(w.s.read_json(output/'status.json')['state'], state)

    def test_unpromoted_preflight_does_not_consume_baseline_or_execute(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d); (path/'soc').mkdir()
            args = argparse.Namespace(soc_build=path/'soc', output=path/'out', timeout=1,
                                      expected_soc_sha256='0'*64, preflight_only=True)
            with patch.object(w, 'checked_soc', side_effect=ValueError('unpromoted')), \
                 patch.object(w.baseline, 'Consumer') as consumer, patch.object(w.Execution, 'execute') as execute:
                with self.assertRaisesRegex(ValueError, 'unpromoted'): w.run(args)
                consumer.assert_not_called(); execute.assert_not_called()
            self.assertEqual(w.s.read_json(path/'out/result.json')['state'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
