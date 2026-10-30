"""Offline admission mutations and private mock execution; no EDA."""
import argparse
import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('canonical_q4_test_subject', Path(__file__).with_name('run.py'))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
s = w.s
clone = w.canonical.build.clone


class AdmissionTests(unittest.TestCase):
    def changed(self, name, mutate):
        path = w.PROGRAM / name
        report = copy.deepcopy(s.read_json(path))
        mutate(report)
        private = SimpleNamespace(**vars(s))
        private.read_json = lambda p: copy.deepcopy(report) if Path(p) == path else s.read_json(p)
        return clone(w.checked_program, {'s': private})

    def test_real_fixed_program_offline(self):
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')):
            report, pins = w.checked_program()
        self.assertEqual(report['elf_sha256'], w.ELF_SHA)
        self.assertGreater(len(pins), 90)
        s.verify_pins(pins)

    def test_receipt_hash_fails_before_parsing(self):
        private = SimpleNamespace(**vars(s))
        private.digest = lambda path: '0' * 64
        private.read_json = lambda path: self.fail('must reject hash before parsing')
        with self.assertRaisesRegex(ValueError, 'receipt SHA'):
            clone(w.checked_program, {'s': private})()

    def test_receipt_flags_and_types_reject(self):
        changes = [('schema', 'old'), ('state', 'PASS'), ('freshpairedexperiment_only', False),
            ('old_cycle_identity_claim', True), ('old_elf_continuation', True),
            ('old_image_validator_called', True), ('timedmachineidentity', True),
            ('timedsource_identical', False), ('timeout_changed', True), ('timeout_seconds', 10801),
            ('restored_nonmain_functions', 35), ('restored_object_tensor_symbols', 31),
            ('all_nonmain_linked_function_bytes_equal', 1), ('zero_new_globals', False),
            ('elf_sha256', '0' * 64), ('preserved_timedsource_hash', '0' * 64)]
        for key, value in changes:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'program review'):
                self.changed('consumer-evidence.json', lambda r: r.update({key: value}))()

    def test_missing_artifact_and_object16_reject(self):
        def drop_artifact(r):
            r['artifact_map'].pop(next(iter(r['artifact_map'])))
        def drop_object(r):
            r['original_16_object_identity_map'].pop(next(iter(r['original_16_object_identity_map'])))
        for mutate, message in ((drop_artifact, 'artifact map'), (drop_object, 'sixteen')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.changed('consumer-evidence.json', mutate)()

    def test_input_maps_and_hash_flags_reject(self):
        with self.assertRaisesRegex(ValueError, 'before/after'):
            self.changed('input-pins-after.json', lambda r: r.pop(next(iter(r))))()
        with self.assertRaisesRegex(ValueError, 'input map references'):
            self.changed('consumer-evidence.json', lambda r: r.update(source_input_map_sha256='0'*64))()

    def test_input_and_artifact_drift_reject(self):
        for name in ('input-pins-before.json', 'consumer-evidence.json'):
            def mutate(r):
                pins = r if name.startswith('input-') else r['artifact_map']
                pins[next(iter(pins))] = '0' * 64
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.changed(name, mutate)()

    def test_layout_timed_and_provenance_mutations_reject(self):
        def layout(r):
            next(iter(r['nonmain_functions'].values()))['bytes_equal'] = False
        for name, mutate in (
            ('layout-review.json', layout),
            ('timed-review.json', lambda r: r.update(old_timed_machine_identity_claimed=True)),
            ('render.json', lambda r: r.update(timed_region_sha256='0' * 64)),
            ('review-result.json', lambda r: r.update(nonmain_function_count=35)),
            ('link-review.json', lambda r: r.update(main_binary_patched=True))):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.changed(name, mutate)()

    def test_canonical_pin_collisions_reject(self):
        canonical = SimpleNamespace(checked_soc=lambda *a: ({}, {'collision': 'b' * 64}, {}))
        prepare = clone(w.prepare_inputs, {'checked_program': lambda: ({}, {'collision': 'a' * 64}),
                                          'canonical': canonical})
        with self.assertRaisesRegex(ValueError, 'Conflicting pin'):
            prepare(w.SOC_BUILD)

    def test_real_canonical_preparation_no_process(self):
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('offline only')):
            program, soc, pins, image = w.prepare_inputs(w.SOC_BUILD)
        self.assertEqual(program['elf_sha256'], w.ELF_SHA)
        self.assertEqual(soc['schema'], 'canonical_soc_v1')
        self.assertTrue(image.items() <= pins.items())
        for name in ('run.py', 'test_run.py', 'README.md'):
            self.assertEqual(pins[str(w.HERE / name)], s.digest(w.HERE / name))

    def test_real_admission_full_preflight_no_subprocess(self):
        class NoPhases(w.Execution):
            def execute(self, *args):
                raise AssertionError('preflight must not execute phases')
        run = clone(w.run, {'Execution': NoPhases})
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', side_effect=AssertionError('no subprocess')):
            output = Path(d) / 'preflight'
            result = run(argparse.Namespace(soc_build=w.SOC_BUILD, output=output,
                                           timeout=10800, preflight_only=True))
            self.assertEqual(result['state'], 'CANONICAL_Q4_HSB_PREFLIGHT_NOT_RUN')
            self.assertEqual(result['elf_sha256'], w.ELF_SHA)
            self.assertEqual(result['soc_build_sha256'], w.SOC_SHA)
            self.assertEqual(result['simulations_launched'], 0)
            self.assertFalse(result['independent_protocol_checked'])
            self.assertNotIn('acceptance', result)
            s.verify_pins(s.read_json(output / 'source-pins.json'))
            self.assertIsNone(s.read_json(output / 'status.json')['child_pid'])


class WorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Existing synthetic fixture, with the real current VLSU schema.
        import test_threeway_attention_check as fixture
        fixture.ThreewayCheckTest.setUpClass()
        cls.text = fixture.ThreewayCheckTest().transcript(1)
        cls.gold = fixture.ThreewayCheckTest.gold

    def exercise(self, base, preflight=False, failure=None, bad_raw=False, protocol_drift=False,
                 admission_failure=False):
        build = base / 'build'; build.mkdir()
        work = base / 'out/work'
        gold = base / 'input/gold.bin'
        gold.parent.mkdir()
        gold.write_bytes(self.gold)
        elf = base / 'fixed.elf'; elf.write_text('mock elf')
        report = {'elf': str(elf), 'elf_sha256': s.digest(elf)}
        simv = build / 'simv'; simv.write_text('mock image')
        image = s.hashes([simv])
        pins = s.hashes([elf, simv, gold, w.RTL])
        calls = []
        outer = self
        class Owner:
            def __init__(self, out):
                self.out = out; self.state = {'child_pid': None}; self.env = {}
            def save(self):
                s.atomic_json(self.out / 'status.json', self.state)
            def execute(self, argv, log, timeout, phase):
                calls.append((phase, list(map(str, argv)), timeout))
                if phase == 'RUNNING' and failure is not None:
                    log.write_text('partial evidence')
                    raise failure
                log.write_text('mock closed phase')
                s.atomic_json(log.with_suffix('.command.json'), {'argv': list(map(str, argv))})
                if phase == 'RUNNING':
                    text = outer.text.replace('commands=8', 'commands=7', 1) if bad_raw else outer.text
                    (work / 'run.vcs.log').write_text(text)
                    (work / 'vector_trace.csv').write_text('mock trace')
                if phase == 'CHECKING':
                    s.atomic_json(work / 'uvm_result.json', dict(status='PASS', issues=[],
                        elf_sha256=report['elf_sha256'], sim_image_sha256=image,
                        log_sha256='0' * 64 if protocol_drift else s.digest(work / 'run.vcs.log'),
                        vector_trace_sha256=s.digest(work / 'vector_trace.csv')))
                self.state[phase.lower() + '_exit_code'] = 0
        private_s = SimpleNamespace(**vars(s))
        private_s.image_files = lambda path: [simv]
        def prepare(path):
            if admission_failure:
                raise ValueError('admission failed')
            return report, {'simv': str(simv)}, dict(pins), image
        check_protocol = clone(w.protocol, {'s': private_s})
        run = clone(w.run, dict(Execution=Owner, prepare_inputs=prepare, s=private_s,
                               GOLD=gold, protocol=check_protocol))
        args = argparse.Namespace(soc_build=build, output=base / 'out', timeout=10800, preflight_only=preflight)
        if failure is not None or bad_raw or protocol_drift or admission_failure:
            with self.assertRaises(Exception):
                run(args)
            result = s.read_json(base / 'out/result.json')
        else:
            result = run(args)
        return result, calls, s.read_json(base / 'out/status.json')

    def test_preflight_no_process_no_simulation_pass(self):
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')):
            result, calls, status = self.exercise(Path(d), preflight=True)
        self.assertEqual(calls, [])
        self.assertEqual(result['state'], 'CANONICAL_Q4_HSB_PREFLIGHT_NOT_RUN')
        self.assertEqual(result['execution'], 'NOT_RUN')
        self.assertEqual(result['simulations_launched'], 0)
        self.assertNotIn('simulator_exit_code', result)
        self.assertIsNone(status['child_pid'])

    def test_real_checker_mock_finalization_pass(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            result, calls, status = self.exercise(base)
            self.assertEqual(result['state'], 'PASS')
            self.assertEqual([p for p, _, _ in calls], ['MANIFEST_BEFORE', 'IMAGE_CONTRACT', 'RUNNING', 'CHECKING', 'MANIFEST_AFTER'])
            run = next((a, t) for p, a, t in calls if p == 'RUNNING')
            self.assertEqual(run[0], list(map(str, w.simulation_command(base/'build/simv', base/'fixed.elf', base/'out/work'))))
            self.assertEqual(run[1], 10800)
            uv = next(a for p, a, _ in calls if p == 'CHECKING')
            for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write'):
                self.assertEqual(uv.count(flag), 1)
            self.assertFalse(any('filter' in a or 'waive' in a for a in uv))
            self.assertEqual(len(result['raw_replay']['trials']), 6)
            self.assertEqual(len(result['raw_replay']['hardware_records']), 16)
            self.assertTrue(result['new_paired_experiment'])
            self.assertFalse(result['old_cycle_identity'])
            s.verify_pins(result['evidence_sha256'])
            self.assertEqual(status['state'], 'PASS')
            self.assertIsNone(status['child_pid'])

    def test_numerical_and_protocol_failures_never_pass(self):
        for options in ({'bad_raw': True}, {'protocol_drift': True}, {'admission_failure': True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as d:
                result, calls, status = self.exercise(Path(d), **options)
                self.assertEqual(result['state'], 'FAIL')
                self.assertNotIn('acceptance', result)
                self.assertEqual(status['state'], 'FAIL')
                self.assertIsNone(status['child_pid'])
                if options.get('admission_failure'):
                    self.assertEqual(calls, [])
                self.assertIn('partial_evidence_sha256', result)

    def test_timeout_interrupt_and_failure_no_retry(self):
        for exc, state in ((subprocess.TimeoutExpired('mock', 10800), 'TIMEOUT'),
                           (InterruptedError('mock'), 'INTERRUPTED'), (ValueError('exit nonzero'), 'FAIL')):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as d:
                result, calls, status = self.exercise(Path(d), failure=exc)
                self.assertEqual(result['state'], state)
                self.assertEqual(result['simulations_launched'], 1)
                self.assertEqual([p for p, _, _ in calls].count('RUNNING'), 1)
                self.assertNotIn('CHECKING', [p for p, _, _ in calls])
                self.assertEqual(status['state'], state)
                self.assertIsNone(status['child_pid'])
                self.assertIn('finished', status)
                self.assertIn(str(Path(d)/'out/work/console.log'), result['partial_evidence_sha256'])

    def test_bound_is_not_adjustable(self):
        for timeout in (True, 0, 10799, 10801):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, 'fixed'):
                w.run(argparse.Namespace(timeout=timeout))

    def test_unchanged_strict_q4_checker_mutations(self):
        self.assertEqual(Path(w.checker.check_log.__code__.co_filename).resolve(),
                         w.HERE.parent / 'check_threeway_attention.py')
        work = next(line for line in self.text.splitlines() if line.startswith('[QBS_PERF]'))
        variants = [self.text.replace('trial=1 mode=1', 'trial=1 mode=2', 1),
                    self.text.replace('commands=8', 'commands=7', 1),
                    self.text.replace('hex=3f800000', 'hex=', 1),
                    self.text.replace('fcsr=1', 'fcsr=3', 1),
                    self.text.replace('vcsr=5', 'vcsr=4', 1),
                    self.text.replace(work + '\n', '', 1),
                    self.text.replace(work, work + '\n' + work, 1),
                    self.text.replace('success=1', 'success=0', 1)]
        for i, text in enumerate(variants):
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                w.checker.check_log(text, 1, self.gold, w.RTL.read_text())


if __name__ == '__main__':
    unittest.main()
