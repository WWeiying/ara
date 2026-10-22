"""Host-only checks. No test invokes VCS, a build or a service manager."""
from dataclasses import asdict, dataclass
from pathlib import Path
import signal
import sys
import tempfile
import threading
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import regression as r


@dataclass
class Result:
    name: str
    kind: str
    status: str
    returncode: int
    elapsed_s: float
    reason: str
    artifact_dir: Path


def dump(path, value):
    r.save(path, value)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=r.HERE, prefix='host_fixture_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.abort = threading.Event()

    def case(self, name='one'):
        elf = self.root / (name + '.elf')
        elf.write_bytes(b'host-only-elf-' + name.encode())
        return dict(id=name, elf=str(elf), sha256=r.sha(elf), original_name=name,
                    timeout_s=180, pass_markers=['FULL_ORACLE_PASS'])

    def fixture(self, case, root=None):
        root = root or self.root / 'artifacts'
        (root / 'work').mkdir(parents=True)
        (root / 'input.elf').write_bytes(Path(case['elf']).read_bytes())
        lines = case.get('oracle_lines', case['pass_markers'])
        text = '\n'.join(lines + [r.SUCCESS, '$finish']) + '\n'
        (root / 'console.log').write_text(text)
        (root / 'work/run.vcs.log').write_text(text)
        ledger = dict(simv='/host-fixture/not-executed/simv', files={'fake-image': 'hash'})
        dump(root / 'inputs.json', dict(binary=dict(source=case['elf'], path=str(root / 'input.elf'),
                                                   sha256=case['sha256']),
                                       simv=dict(path=ledger['simv'], image_sha256=ledger['files'])))
        dump(root / 'command.json', dict(cwd=str(root / 'work'), command=[ledger['simv'], '-l',
             'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(root / 'input.elf'),
             '+TESTCASE=' + case['original_name'], '+NO_FSDB', '+COMMIT_TRACE=' + str(root / 'commit_trace.csv')]))
        (root / 'commit_trace.csv').write_text('cycle,event,order\n1,retire,0\n2,retire,1\n')
        dump(root / 'trace_summary.json', dict(status='VALID'))
        return Result(case['id'], 'app', 'PASS', 0, 1, '', root), ledger

    def wrapper(self, case, result, ledger, controls=None, effect=None):
        class Parent:
            def __init__(self):
                self.cancel_event = threading.Event()

            def _run_test(self, test, image):
                if self.cancel_event.is_set():
                    return Result(test.name, 'app', 'CANCELLED', None, 0, '', result.artifact_dir)
                if effect:
                    effect()
                return result
        return r.checked_runner(Parent, {case['id']: case}, ledger, self.abort,
                                lambda _: None, controls or {})()

    def test_exact48_scope_38_budgets_and_16_reuse(self):
        cases, controls, pins = r.original_scope()
        self.assertEqual(len(cases), 48)
        self.assertEqual(len(controls), 16)
        self.assertEqual(sum(c['timeout_s'] for c in cases if c['stage'] == 'original38'), 16200)
        self.assertEqual(sum(c['timeout_s'] for c in cases if c['stage'] == 'smokes10'), 1800)
        self.assertEqual(sum(not c['id'].startswith('smoke__') for c in controls), 6)
        r.base.verify_pins(pins)

    def test_raw_oracles_on_all48_existing_m4_logs(self):
        cases, controls, _ = r.original_scope()
        baseline = {c['id']: Path(c['baseline_csv']).parent for c in controls}
        for case in cases:
            root = (baseline[case['id']] if case['stage'] == 'smokes10' else
                    r.HERE.parent / 'integration/candidate04_regression38_03/replay/tests' / case['id'])
            with self.subTest(case=case['id']):
                r.check_console(case, (root / 'console.log').read_text())
                self.assertFalse(r.BAD.search((root / 'work/run.vcs.log').read_text()))

    def test_explicit_gates_before_io_or_simulation(self):
        with patch.object(r, 'image_context') as context:
            with self.assertRaises(ValueError):
                r.prepare(self.root, self.root / 'no-create', 0, False)
            with self.assertRaises(ValueError):
                r.run(self.root, self.root / 'no-create', None, False)
            context.assert_not_called()
            self.assertFalse((self.root / 'no-create').exists())

    def test_prepare_on_readonly_m4_then_wrong_image_gate(self):
        image = Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
        out = self.root / 'prepare_only'
        r.prepare(image, out, 0, True)
        data = r.read(out / 'plan.json')
        r.validate_plan(data, image)
        self.assertEqual(data['status'], 'PREPARED_NOT_RUN')
        self.assertFalse((out / 'launch.json').exists())
        self.assertFalse((out / 'original38').exists())
        data['image_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            r.validate_plan(data, image)

    def test_positive_artifact_identity(self):
        case = self.case()
        result, ledger = self.fixture(case)
        r.check_artifacts(result, case, ledger)
        got = self.wrapper(case, result, ledger)._run_test(SimpleNamespace(name=case['id']), None)
        self.assertEqual(got.status, 'PASS')
        self.assertFalse(self.abort.is_set())

    def test_raw_new_failure_markers_cancel(self):
        for marker in ('MATRIX_FAIL', 'EXTENSION_MATRIX_FAIL', 'EXTENDED_FAIL', 'EPOCH_FAIL',
                       'RVV_GATHER_FAIL', 'BOARD_CASE_FAIL', 'BOARD_REPLAY_TRAP', 'FAILED.',
                       'Fatal: assertion', 'UVM_FATAL : 1', 'SKIP'):
            with self.subTest(marker=marker):
                self.abort.clear()
                case = self.case(marker.split()[0].replace(':', ''))
                result, ledger = self.fixture(case, self.root / ('a' + str(len(list(self.root.iterdir())))))
                with (result.artifact_dir / 'console.log').open('a') as f:
                    f.write(marker)
                runner = self.wrapper(case, result, ledger)
                with self.assertRaises(ValueError):
                    runner._run_test(SimpleNamespace(name=case['id']), None)
                self.assertTrue(self.abort.is_set())
                self.assertEqual(runner._run_test(SimpleNamespace(name=case['id']), None).status, 'CANCELLED')

    def test_missing_oracle_and_missing_finish(self):
        case = self.case()
        for text in (r.SUCCESS + '\n$finish', 'FULL_ORACLE_PASS\n' + r.SUCCESS):
            with self.assertRaises(ValueError):
                r.check_console(case, text)

    def test_smoke_all_subcases_required(self):
        case = self.case()
        case['oracle_lines'] = ['Checking the results of the test case 1:', 'PASSED.', 'PASSED: original.c!']
        good = '\n'.join(case['oracle_lines'] + case['pass_markers'] + [r.SUCCESS, '$finish'])
        r.check_console(case, good)
        with self.assertRaises(ValueError):
            r.check_console(case, good.replace('PASSED.\n', ''))

    def test_worker_read_error_cancels(self):
        case = self.case()
        result, ledger = self.fixture(case)
        (result.artifact_dir / 'console.log').unlink()
        with self.assertRaises(FileNotFoundError):
            self.wrapper(case, result, ledger)._run_test(SimpleNamespace(name=case['id']), None)
        self.assertTrue(self.abort.is_set())

    def test_vcs_log_failure_veto(self):
        case = self.case()
        result, ledger = self.fixture(case)
        (result.artifact_dir / 'work/run.vcs.log').write_text('EPOCH_FAIL')
        with self.assertRaises(ValueError):
            self.wrapper(case, result, ledger)._run_test(SimpleNamespace(name=case['id']), None)
        self.assertTrue(self.abort.is_set())

    def test_private_elf_image_and_command_drift(self):
        for mutation in ('elf', 'image', 'command', 'trace'):
            case = self.case(mutation)
            result, ledger = self.fixture(case, self.root / mutation)
            if mutation == 'elf':
                (result.artifact_dir / 'input.elf').write_bytes(b'drift')
            elif mutation == 'image':
                ledger['files'] = {'wrong': 'image'}
            elif mutation == 'command':
                dump(result.artifact_dir / 'command.json', dict(command=['wrong'], cwd='wrong'))
            else:
                dump(result.artifact_dir / 'trace_summary.json', dict(status='INVALID'))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                r.check_artifacts(result, case, ledger)

    def test_pinned_input_drift(self):
        for name in ('input.elf', 'image.json', 'simv', 'runner.py'):
            path = self.root / name
            path.write_bytes(b'before')
            pins = {str(path): r.sha(path)}
            r.base.verify_pins(pins)
            path.write_bytes(b'after')
            with self.assertRaises(ValueError):
                r.base.verify_pins(pins)

    def test_full_csv_cycle_diffs_and_noncycle_failure(self):
        old, new = self.root / 'old.csv', self.root / 'new.csv'
        old.write_text('cycle,event,order\n1,retire,0\n2,retire,1\n')
        new.write_text('cycle,event,order\n2,retire,0\n4,retire,1\n')
        found = r.compare_cycles(old, new, self.root / 'diff.csv')
        self.assertEqual(found['cycle_changed_rows'], 2)
        self.assertEqual(found['last_cycle_delta'], 2)
        for body in ('2,retire,0\n4,retire,3\n', '2,retire,0\n', ''):
            new.write_text('cycle,event,order\n' + body)
            with self.assertRaises(ValueError):
                r.compare_cycles(old, new, self.root / ('diff' + str(new.stat().st_size)))

    def test_cancel_during_actual_csv_validation(self):
        case = self.case()
        result, ledger = self.fixture(case)
        original_compare = r.compare_cycles
        def cancelling_compare(*args):
            finding = original_compare(*args)
            self.abort.set()
            return finding
        controls = {case['id']: dict(baseline_csv=str(result.artifact_dir / 'commit_trace.csv'))}
        with patch.object(r, 'compare_cycles', side_effect=cancelling_compare):
            result = self.wrapper(case, result, ledger, controls)._run_test(SimpleNamespace(name=case['id']), None)
        self.assertEqual(result.status, 'CANCELLED')
        self.assertTrue(self.abort.is_set())

    def test_signal_remains_latched_after_validation(self):
        with r.abort_signals(self.abort):
            signal.raise_signal(signal.SIGTERM)
            self.assertTrue(self.abort.is_set())
            terminal = dict(status='PASS_48_ARCHITECTURAL')
            r.publish(self.root, terminal, self.abort)
        self.assertEqual(r.read(self.root / 'complete.json')['status'], 'NOT_PASS')

    def test_pending_signal_at_publish_vetoes_success(self):
        with r.abort_signals(self.abort):
            old = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})
            try:
                signal.raise_signal(signal.SIGTERM)
                r.publish(self.root, dict(status='PASS_48_ARCHITECTURAL'), self.abort)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, old)
        self.assertTrue(r.read(self.root / 'complete.json')['aborted'])

    def test_interrupted_runner_and_membership_rejected(self):
        case = self.case()
        result, _ = self.fixture(case)
        good = dict(status='COMPLETE', status_counts={'PASS': 1})
        r.check_stage([result], good, [case], self.abort)
        for meta in (dict(good, status='INTERRUPTED'), dict(good, status_counts={'PASS': 0})):
            with self.assertRaises(ValueError):
                r.check_stage([result], meta, [case], self.abort)
        with self.assertRaises(ValueError):
            r.check_stage([result, result], good, [case], self.abort)
        self.abort.set()
        with self.assertRaises(ValueError):
            r.check_stage([result], good, [case], self.abort)

    def test_resource_limits_include_live_and_unused_reservation(self):
        available = 64 * 1024**3
        live = [dict(argv=['simv'], pid=i) for i in range(18)]
        self.assertEqual(r.resource_math(live, available, self.root, 4, 2)['total'], 24)
        with self.assertRaises(ValueError):
            r.resource_math(live, available, self.root, 4, 3)
        with self.assertRaises(ValueError):
            r.resource_math([], 31 * 1024**3, self.root, 4, 0)
        live.append(dict(pid=99, argv=['simv', '+COMMIT_TRACE=' + str(self.root) + '/x.csv']))
        self.assertEqual(r.resource_math(live, available, self.root, 4, 2)['total'], 24)

    def test_resource_process_detection_both_comm_and_argv(self):
        self.assertTrue(r.is_simv('renamed', ['/frozen/image/simv', '+TESTCASE=x']))
        self.assertTrue(r.is_simv('simv', ['/unusual/argv0']))
        self.assertFalse(r.is_simv('python3', ['python3', 'simv']))

    def test_two_stage_host_execution_and_failure_stops_smokes(self):
        # Exercise the real adapter and terminal logic with a fake parent runner.
        # No subprocess is created. Private artifacts still pass the real checker.
        for mode in ('pass', 'fail', 'late_abort'):
            with self.subTest(mode=mode):
                fail = mode == 'fail'
                out = self.root / mode
                out.mkdir()
                image = out / 'image'
                image.mkdir()
                dump(image / 'image.json', {})
                cases = []
                for i in range(48):
                    case = self.case(mode + str(i))
                    case['stage'] = 'original38' if i < 38 else 'smokes10'
                    cases.append(case)
                reference = out / 'reference.csv'
                reference.write_text('cycle,event,order\n1,retire,0\n2,retire,1\n')
                controls = [dict(id=c['id'], name=c['id'], baseline_csv=str(reference)) for c in cases[:16]]
                pins = {str(Path(r.__file__).resolve()): r.sha(Path(r.__file__))}
                pins.update({c['elf']: c['sha256'] for c in cases})
                data = dict(image=str(image), image_sha256=r.sha(image / 'image.json'), snapshot_sha256='snapshot',
                            cases=cases, controls=controls, pins=pins, reserved_slots=0,
                            no_build=True, stop_first_fail=True,
                            stages=[dict(name=n, jobs=j) for n, j in r.STAGES])
                dump(out / 'plan.json', data)
                owner = self
                calls = []
                ledger = dict(simv='/host-fixture/not-executed/simv', files={'fake-image': 'hash'},
                              snapshot_sha256='snapshot')
                class Parent:
                    def __init__(self, opts, tests, argv):
                        self.options, self.tests = opts, tests
                        self.cancel_event = threading.Event()

                    def _run_test(self, test, _):
                        root = self.options.output_root / 'tests' / test.name
                        if self.cancel_event.is_set():
                            return Result(test.name, 'app', 'CANCELLED', None, 0, '', root)
                        calls.append(test.name)
                        case = next(c for c in cases if c['id'] == test.name)
                        result, _ = owner.fixture(case, root)
                        if fail and test.name == cases[0]['id']:
                            with (root / 'console.log').open('a') as stream:
                                stream.write('MATRIX_FAIL')
                        return result

                    def run(self):
                        results = []
                        self.options.output_root.mkdir()
                        for test in self.tests:
                            try:
                                results.append(self._run_test(test, None))
                            except Exception as error:
                                results.append(Result(test.name, 'app', 'ERROR', None, 0, str(error),
                                                      self.options.output_root / 'tests' / test.name))
                        dump(self.options.output_root / 'run.json', dict(
                            status='INTERRUPTED' if self.cancel_event.is_set() else 'COMPLETE',
                            status_counts=dict(r.Counter(x.status for x in results))))
                        dump(self.options.output_root / 'summary.json',
                             [dict(asdict(x), artifact_dir=str(x.artifact_dir)) for x in results])
                        return results

                def options(*args):
                    owner.assertEqual(args[3], 4 if args[1].name == 'original38' else 2)
                    owner.assertEqual(args[5:8], (False, False, True))
                    owner.assertIsNone(args[10])
                    return SimpleNamespace(output_root=args[1])

                def testcase(name, kind, _build, binary, original_name, timeout):
                    owner.assertEqual(timeout, 180)
                    return SimpleNamespace(name=name)

                package, engine = ModuleType('ara_verify'), ModuleType('ara_verify.runner')
                engine.FAIL_RE = r.re.compile('BASE_FAIL')
                package.runner = engine
                identity_calls = 0
                def identity(_image):
                    nonlocal identity_calls
                    identity_calls += 1
                    if mode == 'late_abort' and identity_calls == 3:
                        signal.raise_signal(signal.SIGTERM)
                    return ledger, out, (Parent, options, testcase, None)
                with patch.dict(sys.modules, {'ara_verify': package, 'ara_verify.runner': engine}), \
                     patch.object(r, 'original_scope', return_value=(cases, controls, pins)), \
                     patch.object(r, 'image_context', side_effect=identity), \
                     patch.object(r, 'resources', return_value={'host_fixture': True}):
                    for target in (image / 'image.json', Path(cases[0]['elf'])):
                        content = target.read_bytes()
                        target.write_bytes(b'drift')
                        with self.assertRaises(ValueError):
                            r.run(image, out, r.sha(out / 'plan.json'), True)
                        self.assertEqual(calls, [])
                        self.assertFalse((out / 'launch.json').exists())
                        target.write_bytes(content)
                    code = r.run(image, out, r.sha(out / 'plan.json'), True)
                terminal = r.read(out / 'complete.json')
                self.assertEqual(code, int(mode != 'pass'), terminal)
                self.assertEqual(terminal['aborted'], mode != 'pass')
                self.assertEqual(len(calls), 1 if fail else 48, terminal)
                if fail:
                    self.assertFalse((out / 'smokes10').exists())
                    self.assertEqual(terminal['status'], 'NOT_PASS')
                elif mode == 'late_abort':
                    self.assertEqual(terminal['status'], 'NOT_PASS')
                    self.assertEqual(r.read(out / 'smokes10/run.json')['status'], 'COMPLETE')
                    self.assertEqual(len(terminal['results']), 48)
                else:
                    self.assertEqual(terminal['status'], 'PASS_48_ARCHITECTURAL')
                    self.assertEqual(terminal['performance_status'], 'EXACT_16_CSV')
                    self.assertEqual(len(terminal['results']), 48)
                    r.base.verify_pins(terminal['evidence_pins'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
