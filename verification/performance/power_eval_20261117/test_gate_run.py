"""Host fixtures/mutations only. These are not GLS or measured VCD evidence."""
import importlib.util
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('gate_run_owned', Path(__file__).with_name('gate_run.py'))
g = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g)


def vcd_fixture():
    header = '''$date host fixture $end
$timescale 100 fs $end
$scope module ara_tb $end
$scope module dut $end
$scope module i_ara_soc $end
$var wire 1 ! clk_i $end
$var wire 1 " data $end
$upscope $end
$upscope $end
$upscope $end
$enddefinitions $end
#100000
$dumpvars
0!
1"
$end
'''
    lines = [header]
    for index in range(1, 9):
        lines.append('#%d\n%d!\n' % (100000 + index * 5000, index % 2))
    lines.append('$dumpoff\nx!\nx"\n$end\n')
    return ''.join(lines)


MARKERS = ('GATE_ROI_BEGIN cycle=10 time=100000\n'
           'GATE_CAPTURE_WINDOW_COMPLETE cycle=14 time=140000 task_pass=0\n')


class GateRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='gate-run-host-fixture-')
        self.root = Path(self.tmp.name)
        self.worker_bytes = b'host-only immutable dispatcher fixture\n'
        self.known = patch.dict(g.KNOWN_DISPATCHERS,
            {name: hashlib.sha256(self.worker_bytes).hexdigest() for name in ('precheck.py', 'precheck_v2.py')}, clear=True)
        self.known.start()

    def tearDown(self):
        self.known.stop()
        self.tmp.cleanup()

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def dispatcher(self, name, pid, cases, stages=None, done=None, parallel=3, state='RUNNING', v2=False):
        stages, done = stages or {}, done or {}
        output = self.root / name
        worker_name = 'precheck_v2.py' if v2 else 'precheck.py'
        worker = self.write(name + '/inputs/' + worker_name, self.worker_bytes.decode())
        image = self.root / ('image_' + name)
        plan = dict(image=str(image), parallel=parallel,
                    cases=[dict(id=c, elf=str(self.root / (c + '.elf'))) for c in cases])
        plan_path = self.write(name + '/plan.json', json.dumps(plan))
        pins = {str(worker): g.sha(worker), str(plan_path): g.sha(plan_path)}
        if v2:
            helper = self.write(name + '/inputs/precheck.py', self.worker_bytes.decode())
            pins[str(helper)] = g.sha(helper)
        self.write(name + '/source-pins.json', json.dumps(pins))
        self.write(name + '/attempt.json', json.dumps(dict(pid=pid)))
        self.write(name + '/status.json', json.dumps(dict(state=state, total=len(cases), completed=len(done),
                   cases=[dict(id=c, state=s) for c, s in done.items()])))
        rows = {pid: (1, ['python3', str(worker), 'execute', '--output', str(output)])}
        for c, result in done.items():
            self.write(name + '/runs/' + c + '/result.json', json.dumps(dict(id=c, state=result)))
        for c, (stage, child, live) in stages.items():
            command = ([str(image / 'sim/simv'), '+TESTCASE=' + c,
                        '+PRELOAD=' + str(self.root / (c + '.elf'))] if stage == 'VCS'
                       else ['python3', stage.lower() + '.py', c])
            self.write(name + '/runs/' + c + '/status.json', json.dumps(dict(state=stage, pid=child, command=command)))
            if live:
                rows[child] = (pid, command)
        return rows, output

    def test_limits_and_no_authorization(self):
        g.validate_limits('smoke', None, None, 1000000, 3600, 1024**3, 60)
        g.validate_limits('capture', 10, 14, 20, 3600, 1024**3, 60)
        mutations = [('capture', 0, 14, 20, 3600, 1024**3, 60),
                     ('capture', 10, 11, 20, 3600, 1024**3, 60),
                     ('capture', 10, 5000, 6000, 3600, 1024**3, 60),
                     ('capture', 10, 20, 20, 3600, 1024**3, 60),
                     ('smoke', 10, 14, 20, 3600, 1024**3, 60),
                     ('smoke', None, None, 1000000, 0, 1024**3, 60)]
        for args in mutations:
            with self.subTest(args=args), self.assertRaises(ValueError):
                g.validate_limits(*args)
        with self.assertRaises(ValueError):
            g.execute(self.root, None, None, False)

    def test_exact_markers_and_clean_uart(self):
        self.assertEqual(g.capture_markers(MARKERS, 10, 14), (100000, 140000))
        for text in [MARKERS + MARKERS, MARKERS.replace('task_pass=0', 'task_pass=1'),
                     MARKERS.replace('cycle=14', 'cycle=13'), MARKERS.splitlines()[0],
                     MARKERS + 'Q8_TRAP cause=2\n', MARKERS + 'Fatal: error\n',
                     MARKERS + 'Core Test *** FAILED ***\n', MARKERS + 'UVM_ERROR : 1\n']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                g.capture_markers(text, 10, 14)
        g.clean_log('UVM_ERROR : 0\nUVM_FATAL : 0\nCore Test *** SUCCESS ***\n')

    def test_native_initial_state_clock_and_raw_ticks(self):
        p = self.write('window.vcd', vcd_fixture())
        result = g.validate_vcd(p, 100000, 140000, 4)
        self.assertEqual(result['duration_ticks'], 40000)
        self.assertEqual(result['duration_fs'], 4000000)
        self.assertEqual(result['clock_edges'], 8)
        self.assertTrue(result['complete_initial_state'])

    def test_vcd_mutations(self):
        original = vcd_fixture()
        mutations = [original.replace('1"\n$end', '$end', 1),
                     original.replace('clk_i', 'wrong_clock'),
                     original.replace('100 fs', '1 ps'),
                     original.replace('#100000', '#0'),
                     original.replace('#105000', '#105001'),
                     original.replace('$dumpoff', '$dumpon'),
                     original.replace('#140000', '#145000'),
                     original[:original.index('#140000')],
                     original + '#150000\n1!\n',
                     original.replace('1!\n', 'x!\n', 1)]
        for index, text in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises((ValueError, KeyError)):
                g.validate_vcd(self.write(f'bad{index}.vcd', text), 100000, 140000, 4)

    def test_scope_and_unsupported_baseline(self):
        with self.assertRaises(ValueError):
            g.scoped_output(self.root / 'not-owned')
        with self.assertRaises(ValueError):
            g.admit(self.root, self.root / 'release.json', '0' * 64)

    def test_capture_receipt_is_not_task_pass(self):
        work = self.root / 'run'
        self.write('run/run.vcs.log', MARKERS)
        self.write('run/console.log', MARKERS)
        p = self.write('run/window.vcd', vcd_fixture())
        for name in ('plan.json', 'source-pins.json', 'image-pins.json', 'image-binding.json'):
            self.write(name, '{}')
        stat = p.stat()
        plan = dict(mode='capture', case_id='owned', elf_map=dict(sha256='a' * 64), release='release.json',
                    release_sha256='b' * 64, first_cycle=10, last_cycle=14, max_vcd_bytes=1024**3)
        binding = dict(simv_sha256='c' * 64)
        run = dict(returncode=0, started_ns=min(stat.st_mtime_ns, stat.st_ctime_ns) - 1000000,
                   finished_ns=max(stat.st_mtime_ns, stat.st_ctime_ns) + 1000000)
        result = g.final_check(self.root, plan, binding, run)
        self.assertEqual(result['state'], 'CAPTURE_COMPLETE_NOT_TASK_PASS')
        self.assertFalse(result['full_gate_task_pass'])
        self.assertFalse(result['gate_numeric_checked'])
        self.assertFalse(result['task_pass'])
        self.assertEqual(result['vcd_sha256'], g.sha(p))
        self.assertEqual(result['clock_period_ns'], 1)
        self.assertEqual(result['checked_artifacts'][str(work / 'run.vcs.log')], g.sha(work / 'run.vcs.log'))
        run['started_ns'] = run['finished_ns'] + 10**10
        with self.assertRaises(ValueError):
            g.final_check(self.root, plan, binding, run)

    def test_smoke_runs_pinned_numeric_checker_without_gate_perf(self):
        log = self.write('run/run.vcs.log', 'Core Test *** SUCCESS ***\n')
        self.write('run/console.log', 'Core Test *** SUCCESS ***\n')
        for name in ('plan.json', 'source-pins.json', 'image-pins.json', 'image-binding.json'):
            self.write(name, '{}')
        plan = dict(mode='smoke', case_id=g.Q8, checker=['python3', 'checker.py', '--log', '{log}', '--output', '{result}'],
                    elf_map=dict(sha256='a' * 64), release='release.json', release_sha256='b' * 64)
        def checker(argv, **kwargs):
            self.assertIn(str(log), argv)
            output = Path(argv[argv.index('--output') + 1])
            output.write_text(json.dumps(dict(state='PASS', log_sha256=g.sha(log))))
        with patch.object(g.subprocess, 'run', side_effect=checker) as tool:
            result = g.final_check(self.root, plan, dict(simv_sha256='c' * 64), dict(returncode=0))
        tool.assert_called_once()
        self.assertEqual(result['state'], 'GATE_SMOKE_PASS')
        self.assertTrue(result['full_gate_task_pass'])
        self.assertIn('numericproof', result)

    def test_smoke_rejects_partial_success(self):
        self.write('run/run.vcs.log', 'incomplete\n')
        self.write('run/console.log', 'incomplete\n')
        plan = dict(mode='smoke', case_id=g.Q8, elf_map=dict(sha256='a' * 64), release='', release_sha256='b' * 64)
        with self.assertRaises(ValueError), patch.object(g.subprocess, 'run') as tool:
            g.final_check(self.root, plan, dict(simv_sha256='c' * 64), dict(returncode=0))
        tool.assert_not_called()

    def test_slot_accounting_includes_reserved_rtl_slots(self):
        rows, directory = self.dispatcher('queue', 10, ['a', 'b', 'c'])
        rows[20] = (1, ['/x/simv'])
        self.assertEqual(g.reserved_slots(rows), 4)
        self.assertEqual(g.reserved_slots(rows, own_child=20), 3)
        rows[30] = (1, ['python3', '/x/power_eval_20261117/after_compile.py'])
        self.assertEqual(g.reserved_slots(rows), 4)

    def test_stopping_known_workers_release_unused_threads_not_simulator_slots(self):
        native, _ = self.dispatcher('native', 10, ['n1', 'n2', 'n3'],
            stages={'n2': ('VCS', 100, True)}, done={'n1': 'FAIL', 'n3': 'FAIL'}, state='STOPPING_AFTER_FAILURE')
        baseline, _ = self.dispatcher('baseline', 20, ['b1', 'b2', 'b3', 'b4'],
            stages={'b2': ('VCS', 201, True), 'b4': ('VCS', 202, True)},
            done={'b1': 'FAIL', 'b3': 'PASS'}, state='STOPPING_AFTER_FAILURE', v2=True)
        rows = {**native, **baseline}
        self.assertEqual(g.reserved_slots(rows), 3)
        rows[999] = (900, ['/x/simv'])
        self.assertEqual(g.reserved_slots(rows), 4)
        self.assertEqual(g.reserved_slots(rows, own_child=999), 3)
        rows[998] = (901, ['/x/simv'])
        self.assertEqual(g.reserved_slots(rows, own_child=999), 4)
        self.assertEqual(g.MAX_SLOTS, 4)

    def test_checker_stages_free_vcs_capacity_but_pending_cases_keep_reservation(self):
        stages = {'a': ('VCS', 11, True), 'b': ('NUMERICAL', 12, True), 'c': ('PROTOCOL', 13, True)}
        rows, _ = self.dispatcher('all_started', 10, ['a', 'b', 'c'], stages=stages)
        self.assertEqual(g.reserved_slots(rows), 1)
        rows, _ = self.dispatcher('has_pending', 20, ['a', 'b', 'c', 'd'], stages=stages)
        self.assertEqual(g.reserved_slots(rows), 2)

    def test_publication_races_never_release_launch_in_flight(self):
        rows, output = self.dispatcher('mkdir_race', 10, ['a'], parallel=1)
        (output / 'runs/a').mkdir(parents=True)
        self.assertEqual(g.reserved_slots(rows), 1)
        rows, output = self.dispatcher('vcs_race', 20, ['b'],
                                        stages={'b': ('VCS', 21, False)}, parallel=1)
        self.assertEqual(g.reserved_slots(rows), 1)
        command = g.read(output / 'runs/b/status.json')['command']
        rows[21] = (20, command)
        self.assertEqual(g.reserved_slots(rows), 1)
        status = g.read(output / 'runs/b/status.json')
        status['state'] = 'NUMERICAL'
        (output / 'runs/b/status.json').write_text(json.dumps(status))
        self.assertEqual(g.reserved_slots(rows), 4)

    def test_unknown_dispatcher_state_code_plan_and_pid_fail_closed(self):
        rows, output = self.dispatcher('unknown', 10, ['a'])
        state_path = output / 'status.json'
        original = state_path.read_text()
        for state in ['UNRECOGNIZED', 'STOPPING_AFTER_FAILURE']:
            data = json.loads(original)
            data['state'] = state
            state_path.write_text(json.dumps(data))
            self.assertEqual(g.reserved_slots(rows), 4)
        state_path.write_text(original)
        plan_path = output / 'plan.json'
        before = plan_path.read_text()
        plan_path.write_text(before + '\n')
        self.assertEqual(g.reserved_slots(rows), 4)
        plan_path.write_text(before)
        (output / 'attempt.json').write_text(json.dumps(dict(pid=999)))
        self.assertEqual(g.reserved_slots(rows), 4)
        (output / 'attempt.json').write_text(json.dumps(dict(pid=10)))
        (output / 'inputs/precheck.py').write_text('changed worker')
        self.assertEqual(g.reserved_slots(rows), 4)
        rows = {20: (1, ['python3', '/x/inputs/precheck_v3.py', 'execute', '--output', '/x'])}
        self.assertEqual(g.reserved_slots(rows), 4)

    def test_changing_snapshot_fails_closed(self):
        rows, output = self.dispatcher('changing', 10, ['a'],
                                       stages={'a': ('NUMERICAL', 11, False)}, parallel=1)
        status_path = output / 'runs/a/status.json'
        original_read = Path.read_bytes
        reads = 0
        def changing(path):
            nonlocal reads
            data = original_read(path)
            if path == status_path:
                reads += 1
                if reads > 1:
                    return data + b'\n'
            return data
        with patch.object(Path, 'read_bytes', changing):
            self.assertEqual(g.reserved_slots(rows), 4)

    def test_stopping_with_pending_or_unpublished_case_retains_capacity(self):
        rows, output = self.dispatcher('stopping_pending', 10, ['a', 'b', 'c'],
                                       done={'a': 'FAIL'}, state='STOPPING_AFTER_FAILURE')
        self.assertEqual(g.reserved_slots(rows), 2)
        (output / 'runs/b').mkdir()
        self.assertEqual(g.reserved_slots(rows), 2)

    def test_deferred_binding_rejects_unbuilt_image(self):
        self.write('source-pins.json', '{}')
        image = self.root / 'image'
        self.write('plan.json', json.dumps(dict(image=str(image), release=str(image / 'release.json'), release_sha256='a' * 64)))
        self.write('image/build.json', json.dumps(dict(state='FAIL')))
        with patch.object(g, 'admit'), self.assertRaises(ValueError):
            g.bind_image(self.root)
        self.assertFalse((self.root / 'image-binding.json').exists())

    def test_progress_does_not_invent_cycle_counts(self):
        p = self.write('console.log', 'still booting\n')
        self.assertIsNone(g.last_progress(p)['last_observed_cycle'])
        p.write_text(MARKERS + 'QBS_REAL_BENCH compute_cycles=43033\n')
        self.assertEqual(g.last_progress(p)['last_observed_cycle'], 14)
        self.assertEqual(g.last_progress(p)['target_compute_cycles'], 43033)

    def test_wall_watchdog_stops_only_owned_process_without_running_tools(self):
        self.write('inputs/rtl-plan.json', json.dumps(dict(environment={})))
        (self.root / 'run').mkdir()
        plan = dict(slot_seconds=1, wall_seconds=1, max_vcd_bytes=1024**3,
                    max_log_bytes=1024**2, max_cycles=100, command=['not-a-real-simulator'])
        proc = unittest.mock.Mock(pid=123)
        proc.poll.return_value = None
        ticks = iter([0, 0, 0, 2])
        with patch.object(g, 'slot_lock', side_effect=lambda: nullcontext()), \
             patch.object(g, 'process_snapshot', return_value={}), \
             patch.object(g.subprocess, 'Popen', return_value=proc) as spawn, \
             patch.object(g, 'stop_process') as stop, self.assertRaisesRegex(ValueError, 'wall watchdog'):
            g.run_simulator(self.root, plan, clock=lambda: next(ticks))
        spawn.assert_called_once()
        stop.assert_called_once_with(proc)


if __name__ == '__main__':
    unittest.main()
