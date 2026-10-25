"""Host-only mutation tests and mocked lifecycle; never invoke EDA."""
import argparse
import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('phase_worker_test_subject', Path(__file__).with_name('run.py'))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
s = w.s
clone = w.accepted.canonical.build.clone


def fixture():
    import test_threeway_attention_check as predecessor_fixture
    predecessor_fixture.ThreewayCheckTest.setUpClass()
    old = predecessor_fixture.ThreewayCheckTest().transcript(1).splitlines()
    # Host fixture only: three synthetic calls, never a worker transcript conversion.
    stop = next(i for i, line in enumerate(old) if line.startswith('QUANT_THREEWAY_BEGIN trial=3'))
    lines = [line.replace('QUANT_THREEWAY_', w.checker.PREFIX).replace('trials=6', 'trials=3')
             for line in old[:stop]]
    return '\n'.join(lines+[w.checker.SUITE, w.checker.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']), predecessor_fixture.ThreewayCheckTest.gold


class DiagnosticCheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.gold = fixture()
        cls.rtl = w.accepted.RTL.read_text()

    def test_three_real_calls_only(self):
        result = w.checker.check_log(self.text, self.gold, self.rtl)
        self.assertEqual([t['mode'] for t in result['trials']], [0, 1, 2])
        self.assertEqual(sum(len(t['output_bits']) for t in result['trials']), 2304)
        self.assertEqual(len(result['hardware_records']), 8)
        self.assertEqual(result['repeat_checks'], 0)
        self.assertFalse(result['performance_acceptance'])

    def test_mutations_reject(self):
        work = next(line for line in self.text.splitlines() if line.startswith('[QBS_PERF]'))
        changes = [('trial=1 mode=1', 'trial=1 mode=2'), ('quantizations=6', 'quantizations=5'),
            ('dots=768', 'dots=767'), ('calls=768', 'calls=8'), ('values=128', 'values=768'),
            ('commands=8', 'commands=7'), ('copied=9216', 'copied=0'), ('groups=1', 'groups=0'),
            ('panels=4', 'panels=3'), ('map=0', 'map=1'), ('status=0', 'status=1'),
            ('selection=0', 'selection=1'), ('executor=0', 'executor=1'),
            ('fcsr=1', 'fcsr=33'), ('vcsr=5', 'vcsr=4'), ('errors=0', 'errors=1'),
            ('hex=3f800000', 'hex=7fc00000'), ('hex=3f800000', 'hex='),
            ('max_abs=00000000', 'max_abs=3f800000'), ('pair_bits_differ=0', 'pair_bits_differ=1'),
            ('UVM_ERROR : 0', 'UVM_ERROR : 1'), ('success=1', 'success=0'),
            (work+'\n', ''), (work, work+'\n'+work), (w.checker.SUITE, ''),
            (w.checker.TERMINAL, ''), ('trials=3', 'trials=6')]
        for old, new in changes:
            with self.subTest(old=old), self.assertRaises(ValueError):
                w.checker.check_log(self.text.replace(old, new, 1), self.gold, self.rtl)
        for extra in (w.checker.SUITE, w.checker.capability(), 'QUANT_THREEWAY_SUITE_PASS',
                      'QUANT_DIAG_HSB_UNKNOWN', 'UVM_FATAL : 0'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                w.checker.check_log(self.text+'\n'+extra, self.gold, self.rtl)

    def test_hs_exact_and_b_tolerance_every_output(self):
        for trial in (0, 1, 2):
            lines = self.text.splitlines()
            index = next(i for i, line in enumerate(lines) if line.startswith(f'{w.checker.PREFIX}RESULT trial={trial}'))
            line = lines[index]
            lines[index] = line[:-8]+'40000000'
            with self.subTest(trial=trial), self.assertRaisesRegex(ValueError, 'golden mismatch'):
                w.checker.check_log('\n'.join(lines), self.gold, self.rtl)
        # One ULP at 1.0 is 0x34000000: supply correct self-reported metrics.
        for trial in (1, 2):
            lines = self.text.splitlines()
            index = next(i for i, line in enumerate(lines) if line.startswith(f'{w.checker.PREFIX}RESULT trial={trial}'))
            lines[index] = lines[index].replace('hex=3f800000', 'hex=3f800001', 1).replace(
                'max_abs=00000000 pair_max_abs=00000000 pair_bits_differ=0',
                'max_abs=34000000 pair_max_abs=34000000 pair_bits_differ=1')
            if trial == 1:
                with self.assertRaisesRegex(ValueError, 'Shared RVV changed arithmetic'):
                    w.checker.check_log('\n'.join(lines), self.gold, self.rtl)
            else:
                self.assertEqual(len(w.checker.check_log('\n'.join(lines), self.gold, self.rtl)['trials']), 3)

    def test_frozen_six_call_checker_unchanged_and_separate(self):
        self.assertEqual(s.digest(w.PHASE.parent/'check_threeway_attention.py'),
                         'ac2fecc27be77220a442bfdfb2292c37a9fe585148d4fe79da9aae09ff34dd05')
        with self.assertRaises(ValueError):
            w.accepted.checker.check_log(self.text, 1, self.gold, self.rtl)


class AdmissionTests(unittest.TestCase):
    def prepared_receipt(self):
        receipt = w.PHASE/'prepare/out/build-gnu-02/build.json'
        self.assertTrue(receipt.is_file(), 'Need final build-gnu-02 receipt')
        self.assertEqual(s.read_json(receipt)['state'], 'DIAGNOSTIC_GNU_STATIC_PASS_NOT_EXECUTED')
        return receipt

    def test_parent_hash_before_parse(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'review.json'
            path.write_text('not json')
            with self.assertRaisesRegex(ValueError, 'Parent review SHA'):
                w.checked_review(path, '0'*64)

    def test_real_prepared_program_static_replay_no_process(self):
        receipt = self.prepared_receipt()
        pins = s.hashes(p for p in (w.PHASE/'prepare').iterdir() if p.is_file())
        pins[str(receipt)] = s.digest(receipt)
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('host-only')):
            report, pins = w.checked_program({}, receipt, pins)
        self.assertEqual(report['trials'], 3)
        self.assertEqual(report['simulations_launched'], 0)
        self.assertGreater(len(pins), 90)
        s.verify_pins(pins)

    def test_program_receipt_bad_types_and_claims(self):
        receipt = self.prepared_receipt()
        original = s.read_json(receipt)
        for key, value in (('trials', 6), ('diagnostic_only', 1), ('performance_claim', True),
                           ('repeat_checks', 1), ('post_pins_match', False),
                           ('accepted_six_call_evidence_replaced', True), ('state', 'PASS')):
            private = SimpleNamespace(**vars(s))
            changed = dict(original, **{key: value})
            private.read_json = lambda path: changed if Path(path) == receipt else s.read_json(path)
            pins = s.hashes(p for p in (w.PHASE/'prepare').iterdir() if p.is_file())
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'program fields'):
                clone(w.checked_program, {'s': private})({}, receipt, pins)

    def test_real_canonical_and_program_admission_offline(self):
        receipt = self.prepared_receipt()
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            phase_map = base/'phase-map.json'
            s.atomic_json(phase_map, dict(schema='quantkv_phase_map_v1', functions={}, ranges=[]))
            helpers = s.hashes(p for directory in (w.PHASE/'prepare', w.PHASE/'analysis')
                              for p in directory.iterdir() if p.is_file() and
                              (p.suffix == '.py' or p.name in ('README.md', '.gitignore')))
            (base/'review').mkdir()
            review = base/'review/review.json'
            s.atomic_json(review, dict(schema='quant_hsb_phase_worker_review_v1',
                program_receipt=str(receipt), program_receipt_sha256=s.digest(receipt),
                helper_pins=helpers, phase_map=str(phase_map), phase_map_sha256=s.digest(phase_map),
                runtime_environment={'LD_LIBRARY_PATH': os.environ.get('LD_LIBRARY_PATH')}))
            args = argparse.Namespace(review=review, review_sha256=s.digest(review),
                output=base/'output/run', soc_build=w.accepted.SOC_BUILD, timeout=10800,
                execute_reviewed_diagnostic=False)
            with patch.object(subprocess, 'Popen', side_effect=AssertionError('offline only')):
                result = w.run(args)
            self.assertEqual(result['state'], 'DIAGNOSTIC_PREFLIGHT_NOT_RUN')
            self.assertEqual(result['simulations_launched'], 0)
            self.assertFalse(result['retirement_analysis_checked'])
            self.assertEqual(result['runtime_environment'], {'LD_LIBRARY_PATH': os.environ.get('LD_LIBRARY_PATH')})
            s.verify_pins(s.read_json(args.output/'source-pins.json'))


class LifecycleTests(unittest.TestCase):
    def exercise(self, base, execute=True, failure=None, bad_raw=False, bad_protocol=False,
                 bad_analysis=False, drift=False, admission_failure=False, environment_drift=False,
                 wrong_environment_review=False):
        text, gold_data = fixture()
        build = base/'build'; build.mkdir()
        review_dir = base/'review'; review_dir.mkdir()
        review = review_dir/'review.json'
        s.atomic_json(review, {'runtime_environment': {'LD_LIBRARY_PATH':
                      '/different/lib' if wrong_environment_review else '/accepted/vendor/lib'}})
        elf = base/'program.elf'; elf.write_bytes(b'mock ELF')
        simv = build/'simv'; simv.write_bytes(b'mock image')
        (base/'input').mkdir()
        gold = base/'input/gold.bin'; gold.write_bytes(gold_data)
        out, work = base/'out', base/'out/work'
        image = s.hashes([simv])
        pins = s.hashes([elf, simv, gold, w.accepted.RTL])
        report = dict(elf=str(elf), elf_sha256=s.digest(elf))
        args = argparse.Namespace(timeout=10800, soc_build=build, output=out, review=review,
            review_sha256=s.digest(review), execute_reviewed_diagnostic=execute)
        calls = []

        class Owner:
            def __init__(self, output):
                self.out, self.env, self.state = output, {'LD_LIBRARY_PATH': '/accepted/vendor/lib'}, {'child_pid': None}
            def save(self):
                s.atomic_json(self.out/'status.json', self.state)
            def execute(self, argv, log, timeout, phase):
                calls.append((phase, list(map(str, argv)), timeout))
                log.write_text('closed mock phase')
                if failure and phase == failure[0]:
                    raise failure[1]
                if phase == 'RUNNING':
                    (work/'run.vcs.log').write_text(text.replace('commands=8', 'commands=7', 1) if bad_raw else text)
                    (work/'commit_trace.csv').write_text('full mock scalar trace')
                    (work/'vector_trace.csv').write_text('full mock vector trace')
                    if drift:
                        elf.write_bytes(b'drift')
                    if environment_drift:
                        self.env['LD_LIBRARY_PATH'] = '/drift/lib'
                if phase == 'CHECKING':
                    s.atomic_json(work/'uvm_result.json', dict(status='PASS', issues=[],
                        elf_sha256=report['elf_sha256'], sim_image_sha256=image,
                        log_sha256='0'*64 if bad_protocol else s.digest(work/'run.vcs.log'),
                        vector_trace_sha256=s.digest(work/'vector_trace.csv')))
                if phase == 'ANALYZING':
                    trials = w.checker.check_log(text, gold_data, w.accepted.RTL.read_text())['trials']
                    result = dict(schema='quantkv_phase_analysis_v1', state='DIAGNOSTIC_RETIREMENT_PROVEN',
                        diagnostic_only=True, scalar_trace_truncated=bad_analysis, csr_reads=6,
                        functional_acceptance=False, hardware_utilization_claimed=False,
                        performance_acceptance=False, pre_post_pins_match=True,
                        elf_sha256=report['elf_sha256'], input_pins=s.hashes([elf, work/'run.vcs.log',
                        work/'commit_trace.csv', work/'vector_trace.csv']), input_manifest_sha256=s.digest(work/'analysis-inputs.json'),
                        measurement_pcs=['0x1000', '0x1004'], windows=[dict(trial=t['trial'], mode=t['mode'],
                            cycles=t['cycles'], csr_cycle_delta=t['cycles'], retired_instructions=12,
                            qbs_command_words=['06b5045b', '02b5045b']*4 if t['mode'] == 2 else []) for t in trials])
                    s.atomic_json(work/'analysis.json', result)
                self.state[phase.lower()+'_exit_code'] = 0

        private = SimpleNamespace(**vars(s))
        private.image_files = lambda _: [simv]
        accepted = SimpleNamespace(**vars(w.accepted))
        accepted.GOLD = gold
        def prepare(_):
            if admission_failure:
                raise ValueError('admission failed')
            return report, dict(simv=str(simv)), dict(pins), image
        def analysis_inputs(*_):
            path = work/'analysis-inputs.json'; s.atomic_json(path, {'mock': True})
            return path, s.digest(path)
        run = clone(w.run, dict(Execution=Owner, s=private, accepted=accepted,
                               prepare_inputs=prepare, analysis_inputs=analysis_inputs))
        fail = failure or bad_raw or bad_protocol or bad_analysis or drift or admission_failure or environment_drift or wrong_environment_review
        if fail:
            with self.assertRaises(Exception):
                run(args)
            result = s.read_json(out/'result.json')
        else:
            result = run(args)
        return result, calls, s.read_json(out/'status.json')

    def test_default_preflight_no_subprocess(self):
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')):
            result, calls, status = self.exercise(Path(d), execute=False)
        self.assertEqual(calls, [])
        self.assertEqual(result['state'], 'DIAGNOSTIC_PREFLIGHT_NOT_RUN')
        self.assertEqual(result['execution'], 'NOT_RUN')
        self.assertEqual(result['simulations_launched'], 0)
        self.assertFalse(result['retirement_analysis_checked'])
        self.assertNotIn('acceptance', result)
        self.assertIsNone(status['child_pid'])

    def test_all_gates_pass_mock_only(self):
        with tempfile.TemporaryDirectory() as d:
            result, calls, status = self.exercise(Path(d))
            s.verify_pins(result['evidence_sha256'])
        self.assertEqual(result['state'], 'PASS')
        self.assertEqual([p for p, _, _ in calls], ['MANIFEST_BEFORE', 'IMAGE_CONTRACT', 'RUNNING',
                                                 'CHECKING', 'ANALYZING', 'MANIFEST_AFTER'])
        command = next(argv for phase, argv, _ in calls if phase == 'RUNNING')
        for flag in ('+COMMIT_TRACE=', '+VECTOR_TRACE='):
            self.assertEqual(sum(arg.startswith(flag) for arg in command), 1)
        self.assertFalse(any('COMMIT_TRACE_LIMIT' in arg for arg in command))
        uv = next(argv for phase, argv, _ in calls if phase == 'CHECKING')
        for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write'):
            self.assertEqual(uv.count(flag), 1)
        self.assertFalse(any('waive' in arg or 'filter' in arg for arg in uv))
        self.assertTrue(result['independent_protocol_checked'])
        self.assertTrue(result['retirement_analysis_checked'])
        self.assertFalse(result['performance_acceptance'])
        self.assertEqual(result['runtime_environment'], {'LD_LIBRARY_PATH': '/accepted/vendor/lib'})
        self.assertIsNone(status['child_pid'])

    def test_missing_checks_and_drift_never_pass(self):
        for options in ({'bad_raw': True}, {'bad_protocol': True}, {'bad_analysis': True},
                        {'drift': True}, {'admission_failure': True}, {'environment_drift': True},
                        {'wrong_environment_review': True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as d:
                result, calls, status = self.exercise(Path(d), **options)
                self.assertEqual(result['state'], 'FAIL')
                self.assertNotIn('acceptance', result)
                self.assertFalse(result['post_pins_match'])
                self.assertEqual(status['state'], 'FAIL')
                self.assertLessEqual(sum(p == 'RUNNING' for p, _, _ in calls), 1)

    def test_all_phase_failures_preserved_no_retry(self):
        for phase in ('MANIFEST_BEFORE', 'IMAGE_CONTRACT', 'RUNNING', 'CHECKING', 'ANALYZING', 'MANIFEST_AFTER'):
            for error, state in ((subprocess.TimeoutExpired('mock', 10800), 'TIMEOUT'),
                                 (InterruptedError('mock'), 'INTERRUPTED'), (ValueError('nonzero'), 'FAIL')):
                with self.subTest(phase=phase, state=state), tempfile.TemporaryDirectory() as d:
                    result, calls, status = self.exercise(Path(d), failure=(phase, error))
                    self.assertEqual(result['state'], state)
                    self.assertNotIn('acceptance', result)
                    self.assertLessEqual(sum(p == 'RUNNING' for p, _, _ in calls), 1)
                    self.assertIn('partial_evidence_sha256', result)
                    self.assertIsNone(status['child_pid'])

    def test_invalid_bounds_before_any_phase(self):
        for timeout in (True, 0, -1, 10801, 1.5):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, 'Timeout'):
                w.run(argparse.Namespace(timeout=timeout))


class RetirementAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = w.PHASE/'analysis'
        path = directory/'test_analyze.py'
        if not path.exists():
            raise unittest.SkipTest('Analysis fixtures not yet published')
        cls.fixtures = w.load('phase_worker_analysis_fixtures', path, s.digest(path))
        cls.adapter = w.load('phase_worker_retirement_adapter', w.HERE/'retirement.py', s.digest(w.HERE/'retirement.py'))
        cls.adapter.worker = w

    def exercise(self, base, mutation=None):
        f = self.fixtures
        binary, assembly = f.fixture_elf()
        instructions = f.a.disassembly_map(assembly, f.a.LinkedELF(binary))
        rows = f.fixture_rows(instructions)
        for row in rows:
            if row['pc'] == 0x1004:
                trial = row['rd_wdata']//1000
                row['rd_wdata'] = trial*1000 + (3000, 2000, 1000)[trial]
        if mutation == 'missing_last_csr':
            rows = rows[:-1]
        elif mutation == 'bad_tail':
            rows.append(dict(rows[-1], pc=0x1008, cycle=999, order=999))
        elif mutation == 'bad_instruction':
            rows[1]['insn'] ^= 2
        text, gold = fixture()
        paths = dict(elf=base/'program.elf', disassembly=base/'disassembly.log', log=base/'run.vcs.log',
                     commit=base/'commit_trace.csv', vector=base/'vector_trace.csv', golden=base/'gold.bin',
                     rtl=w.accepted.RTL, phase_map=base/'phase-map.json')
        paths['elf'].write_bytes(binary)
        paths['disassembly'].write_text(assembly)
        paths['log'].write_text(text)
        paths['commit'].write_text(f.csv_text(rows))
        paths['vector'].write_text('Pinned full vector input; independently checked by UVM in real worker')
        paths['golden'].write_bytes(gold)
        s.atomic_json(paths['phase_map'], dict(schema='quantkv_phase_map_v1', functions={}, ranges=[]))
        pins = w.own_pins()
        s.merge_pins(pins, s.hashes(paths.values()))
        s.merge_pins(pins, s.hashes([w.PHASE/'analysis/analyze.py']))
        inputs = base/'inputs.json'
        s.atomic_json(inputs, dict(schema='quant_hsb_worker_retirement_inputs_v1',
            files={k: str(p) for k, p in paths.items()}, pins=pins, boundary_pcs=[0x1000, 0x1004],
            helper=str(w.PHASE/'analysis/analyze.py')))
        sha = s.digest(inputs)
        if mutation == 'input_drift':
            paths['commit'].write_text('truncated')
        return self.adapter.analyze(inputs, sha, base/'analysis.json')

    def test_real_retirement_engine_and_new_protocol(self):
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', side_effect=AssertionError('host only')):
            result = self.exercise(Path(d))
        self.assertEqual(result['state'], 'DIAGNOSTIC_RETIREMENT_PROVEN')
        self.assertEqual(len(result['windows']), 3)
        self.assertEqual([row['csr_cycle_delta'] for row in result['windows']], [3000, 2000, 1000])
        self.assertFalse(result['scalar_trace_truncated'])
        self.assertFalse(result['performance_acceptance'])

    def test_actual_prepared_elf_disassembly_and_boundaries(self):
        receipt = AdmissionTests().prepared_receipt()
        report = s.read_json(receipt)
        elf = Path(report['elf'])
        engine = self.fixtures.a
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('no subprocess')):
            instructions = engine.disassembly_map((elf.parent/'disassembly.log').read_text(),
                                                  engine.LinkedELF(elf.read_bytes()))
        sites = [pc for pc, item in instructions.items() if engine.is_cycle_read(item)]
        mapping = s.read_json(elf.parent/'object-map.json')
        self.assertEqual(sites, [row['pc'] for row in mapping['rdcycle_sites']])
        self.assertEqual(len(sites), 2)

    def test_actual_native_source_m4_m2_and_linked_encoding(self):
        receipt = AdmissionTests().prepared_receipt()
        directory = receipt.parent
        source_path = w.ROOT/'software/qbs/src/qbs_native_riscv.c'
        source = source_path.read_text()
        old = w.ROOT/'verification/out/akv-quantkv-rvv-qbs-build-20261024-01/source-pins.json'
        self.assertEqual(s.digest(source_path), s.read_json(old)[str(source_path)])
        engine = self.fixtures.a
        instructions = engine.disassembly_map((directory/'disassembly.log').read_text(),
            engine.LinkedELF((directory/'q4_hsb_phase_diagnostic.elf').read_bytes()))
        for rows, word, vset in ((4, 0x06b5045b, 0x0d22f057), (2, 0x02b5045b, 0x0d12f057)):
            block = source.split(f'case {rows}:', 1)[1].split('break;', 1)[0]
            self.assertIn(f'.word 0x{word:08x}', block)
            self.assertIn(f'e32, m{rows}, ta, ma', block)
            sites = [pc for pc, item in instructions.items() if item['bits'] == word]
            self.assertEqual(len(sites), 1)
            self.assertIn('qbs_native_execute_command', instructions[sites[0]]['function'])
            self.assertEqual(instructions[sites[0]-4]['bits'], vset)
        self.assertEqual(engine.CUSTOM_SEQUENCE, [0x06b5045b, 0x02b5045b]*4)

    def test_final_build_actual_inputs_through_retirement_adapter(self):
        # Host-only API integration, NOT a recorded execution/control-flow claim.
        receipt = AdmissionTests().prepared_receipt()
        report = s.read_json(receipt)
        elf = Path(report['elf'])
        engine = self.fixtures.a
        instructions = engine.disassembly_map((elf.parent/'disassembly.log').read_text(),
                                               engine.LinkedELF(elf.read_bytes()))
        boundaries = [row['pc'] for row in s.read_json(elf.parent/'object-map.json')['rdcycle_sites']]
        scalar_pc = next(pc for pc, row in instructions.items() if row['function'] == 'main' and
                         not engine.is_cycle_read(row) and engine.instruction_type(row) == 'scalar_other')
        command_pcs = {item['bits']: pc for pc, item in instructions.items() if item['bits'] in engine.CUSTOM_SEQUENCE}
        rows = []
        def retire(pc, value=0):
            item = instructions[pc]
            row = dict.fromkeys(engine.COMMIT_HEADER, 0)
            row.update(event='retire', cycle=10+2*len(rows), order=len(rows), port=0, trans_id=-1,
                       pc=pc, insn=item['bits'], rd=(item['bits'] >> 7 & 31) if pc in boundaries else 0,
                       rd_wdata=value)
            rows.append(row)
        for trial, cycles in enumerate((3000, 2000, 1000)):
            retire(boundaries[0], 10000*trial)
            retire(scalar_pc)
            if trial == 2:
                for word in engine.CUSTOM_SEQUENCE:
                    retire(command_pcs[word])
            retire(boundaries[1], 10000*trial+cycles)
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            text, _ = fixture()
            golden = w.accepted.GOLD.read_bytes()
            hex_output = ''.join(f'{int.from_bytes(golden[i:i+4], "little"):08x}' for i in range(0, 3072, 4))
            text = text.replace('hex='+'3f800000'*768, 'hex='+hex_output)
            paths = dict(elf=elf, disassembly=elf.parent/'disassembly.log', log=base/'run.vcs.log',
                commit=base/'commit_trace.csv', vector=base/'vector_trace.csv', golden=w.accepted.GOLD,
                rtl=w.accepted.RTL, phase_map=base/'phase-map.json')
            paths['log'].write_text(text)
            paths['commit'].write_text(self.fixtures.csv_text(rows))
            paths['vector'].write_text('synthetic host integration only; not UVM evidence')
            s.atomic_json(paths['phase_map'], dict(schema='quantkv_phase_map_v1', functions={}, ranges=[]))
            pins = w.own_pins()
            s.merge_pins(pins, s.hashes(paths.values()))
            s.merge_pins(pins, s.hashes([w.PHASE/'analysis/analyze.py']))
            inputs = base/'inputs.json'
            s.atomic_json(inputs, dict(schema='quant_hsb_worker_retirement_inputs_v1',
                files={k: str(p) for k, p in paths.items()}, pins=pins, boundary_pcs=boundaries,
                helper=str(w.PHASE/'analysis/analyze.py')))
            with patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')):
                result = self.adapter.analyze(inputs, s.digest(inputs), base/'analysis.json')
            parsed = w.checker.check_log(text, golden, w.accepted.RTL.read_text())
            # checked_analysis expects the ELF and raw evidence in their usual work names.
            self.assertEqual(w.checked_analysis(base, report, parsed)['state'], 'DIAGNOSTIC_RETIREMENT_PROVEN')
            self.assertEqual(result['elf_sha256'], report['elf_sha256'])
            self.assertEqual(len(result['windows']), 3)

    def test_incomplete_corrupt_drift_and_bad_tail_reject(self):
        for mutation in ('missing_last_csr', 'bad_tail', 'bad_instruction', 'input_drift'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
                self.exercise(Path(d), mutation)


if __name__ == '__main__':
    unittest.main()
