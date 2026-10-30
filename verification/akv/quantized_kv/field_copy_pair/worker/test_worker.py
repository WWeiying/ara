"""Private mocked phases and subprocess lifecycle tests; no EDA is invoked."""
import argparse
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as w
import collect as collector
import admission
from test_compare import checked_fixture

s = w.s
clone = w.accepted.canonical.build.clone


class HostFixture:
    def __init__(self, base):
        self.base = base
        self.text, golden, self.parsed = checked_fixture()
        self.build = base/'image'; self.build.mkdir()
        self.simv = self.build/'simv'; self.simv.write_text('mock canonical image')
        self.review_dir = base/'review'; self.review_dir.mkdir()
        self.review_path = self.review_dir/'review.json'
        self.gold_dir = base/'capture'; self.gold_dir.mkdir()
        self.golden = self.gold_dir/'gold.bin'; self.golden.write_bytes(golden)
        self.programs = {}
        for side in w.SIDES:
            directory = base/('program-'+side); directory.mkdir()
            elf = directory/'attention.elf'; elf.write_text('mock '+side+' ELF')
            self.programs[side] = dict(elf=str(elf), elf_sha256=s.digest(elf), golden=str(self.golden),
                golden_sha256=s.digest(self.golden), revision=w.REVISIONS[side], fresh_build=True)
        self.prepared = dict(programs=self.programs)
        self.review = dict(runtime_environment={'LD_LIBRARY_PATH': os.environ.get('LD_LIBRARY_PATH')},
                           prepared_pair_sha256='a'*64)
        s.atomic_json(self.review_path, self.review)
        self.image = s.hashes([self.simv])
        self.pins = s.hashes([self.simv, self.golden, w.accepted.RTL, self.review_path,
                             *[Path(p['elf']) for p in self.programs.values()]])
        self.calls = []

    def args(self, side, execute=True):
        return argparse.Namespace(side=side, timeout=10800, review=self.review_path,
            review_sha256=s.digest(self.review_path), soc_build=self.build,
            output=self.base/side, execute_reviewed_side=execute)

    def prepare(self, args):
        return self.prepared, dict(simv=str(self.simv)), dict(self.pins), dict(self.image), self.review

    def subject(self, failure=None, bad_raw=False, bad_uvm=False, drift=False, env_drift=False):
        fixture = self
        class Owner(w.Execution):
            def execute(self, argv, log, timeout, phase):
                fixture.calls.append((self.out.name, phase, list(map(str, argv)), timeout))
                log.write_text('closed mock phase')
                s.atomic_json(log.with_suffix('.command.json'),
                    dict(argv=list(map(str, argv)), cwd=str(log.parent), timeout_seconds=timeout))
                self.state['state'] = phase
                if failure and phase == failure[0]:
                    raise failure[1]
                work = self.out/'work'
                if phase == 'RUNNING':
                    (work/'run.vcs.log').write_text(fixture.text.replace('commands=8', 'commands=7', 1) if bad_raw else fixture.text)
                    (work/'vector_trace.csv').write_text('mock full vector trace')
                    if drift: fixture.simv.write_text('drift')
                    if env_drift: self.env['LD_LIBRARY_PATH'] = '/drift/lib'
                if phase == 'CHECKING':
                    program = fixture.programs[self.out.name]
                    s.atomic_json(work/'uvm_result.json', dict(status='PASS', issues=[],
                        elf_sha256=program['elf_sha256'], sim_image_sha256=fixture.image,
                        log_sha256='0'*64 if bad_uvm else s.digest(work/'run.vcs.log'),
                        vector_trace_sha256=s.digest(work/'vector_trace.csv')))
                self.state[phase.lower()+'_exit_code'] = 0
                self.save()
        private = SimpleNamespace(**vars(s))
        private.image_files = lambda _: [self.simv]
        return clone(w.run, dict(Execution=Owner, s=private, prepare_inputs=self.prepare))


class SideTests(unittest.TestCase):
    def test_offline_default_no_phases(self):
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')):
            f = HostFixture(Path(d))
            result = f.subject()(f.args('baseline', execute=False))
            self.assertEqual(result['state'], 'FIELD_COPY_SIDE_PREFLIGHT_NOT_RUN')
            self.assertEqual(result['simulations_launched'], 0)
            self.assertEqual(result['execution'], 'NOT_RUN')
            self.assertEqual(f.calls, [])
            self.assertFalse(result['independent_protocol_checked'])

    def test_both_separate_sides_real_original_raw_checker(self):
        with tempfile.TemporaryDirectory() as d:
            f = HostFixture(Path(d))
            for side in w.SIDES:
                result = f.subject()(f.args(side))
                self.assertEqual(result['state'], 'FIELD_COPY_SIDE_CHECKED')
                self.assertEqual(result['output_words_checked'], 4608)
                self.assertEqual(result['native_commands_checked'], 16)
                self.assertFalse(result['performance_acceptance'])
                s.verify_pins(result['evidence_sha256'])
            runs = [row for row in f.calls if row[1] == 'RUNNING']
            self.assertEqual(len(runs), 2)
            for side, _, argv, timeout in runs:
                self.assertEqual(timeout, 10800)
                self.assertFalse(any('COMMIT_TRACE' in item for item in argv))
                self.assertEqual(sum(item.startswith('+VECTOR_TRACE=') for item in argv), 1)
                self.assertIn('+ARA_CONTRACT_TRACE_LIMIT=2000000', argv)
                self.assertIn('+ARA_UVM_TRACE_LIMIT=2000000', argv)
                self.assertIn('+PRELOAD='+f.programs[side]['elf'], argv)
            for side, phase, argv, _ in f.calls:
                if phase == 'CHECKING':
                    for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write'):
                        self.assertEqual(argv.count(flag), 1)
                    self.assertFalse(any('waive' in item or 'filter' in item for item in argv))

    def test_phase_errors_bound_no_retry(self):
        for phase in ('MANIFEST_BEFORE', 'IMAGE_CONTRACT', 'RUNNING', 'CHECKING', 'MANIFEST_AFTER'):
            for exc, state in ((ValueError('nonzero'), 'FAIL'), (InterruptedError('stop'), 'INTERRUPTED'),
                               (subprocess.TimeoutExpired('mock', 10800), 'TIMEOUT')):
                with self.subTest(phase=phase, state=state), tempfile.TemporaryDirectory() as d:
                    f = HostFixture(Path(d))
                    with self.assertRaises(type(exc)):
                        f.subject(failure=(phase, exc))(f.args('baseline'))
                    result = s.read_json(f.base/'baseline/result.json')
                    self.assertEqual(result['state'], state)
                    self.assertFalse(result['post_pins_match'])
                    self.assertIn('partial_evidence_sha256', result)
                    self.assertLessEqual(sum(row[1] == 'RUNNING' for row in f.calls), 1)
                    self.assertIsNone(s.read_json(f.base/'baseline/status.json')['child_pid'])

    def test_bad_raw_uvm_image_or_environment_cannot_pass(self):
        for options in ({'bad_raw': True}, {'bad_uvm': True}, {'drift': True}, {'env_drift': True}):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as d:
                f = HostFixture(Path(d))
                with self.assertRaises(Exception): f.subject(**options)(f.args('candidate'))
                self.assertEqual(s.read_json(f.base/'candidate/result.json')['state'], 'FAIL')

    def test_invalid_timeout_before_admission(self):
        for value in (True, 0, -1, 10801, 2.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Timeout'):
                w.run(argparse.Namespace(timeout=value))


class LifecycleTests(unittest.TestCase):
    def test_private_cwd_and_recorded_owner_no_real_child(self):
        process = SimpleNamespace(pid=123, wait=lambda timeout=None: 0)
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', return_value=process) as popen:
            output = Path(d)
            (output/'work').mkdir()
            owner = w.Execution(output)
            owner.execute(['/mock/simv', '-no_save'], output/'work/console.log', 10800, 'RUNNING')
            self.assertEqual(popen.call_args.kwargs['cwd'], output/'work')
            self.assertTrue(popen.call_args.kwargs['start_new_session'])
            self.assertEqual(owner.state['simulator_pid'], 123)
            self.assertIsNone(owner.state['child_pid'])
            self.assertEqual(s.read_json(output/'work/console.command.json')['cwd'], str(output/'work'))

    def test_timeout_cleans_only_new_child_group(self):
        waits = iter([subprocess.TimeoutExpired('mock', 1), 0, 0])
        def wait(timeout=None):
            value = next(waits)
            if isinstance(value, Exception): raise value
            return value
        process = SimpleNamespace(pid=123, wait=wait)
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', return_value=process), \
                patch.object(os, 'killpg') as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                w.run_command(['/mock/simv'], Path(d)/'console.log', 1, {}, lambda _: None)
            self.assertEqual([c.args[0] for c in kill.call_args_list], [123, 123])


class CollectorTests(unittest.TestCase):
    def exercise(self, base, mutate=None):
        f = HostFixture(base)
        for side in w.SIDES:
            f.subject()(f.args(side))
        if mutate:
            mutate(f)
        args = argparse.Namespace(baseline=base/'baseline', candidate=base/'candidate',
            review=f.review_path, review_sha256=s.digest(f.review_path), soc_build=f.build, output=base/'comparison')
        private = SimpleNamespace(**vars(s))
        private.image_files = lambda _: [f.simv]
        private_worker = SimpleNamespace(**vars(w))
        private_worker.prepare_inputs = f.prepare
        consume = clone(collector.collect, dict(worker=private_worker, s=private))
        return consume(args), f

    def test_offline_replay_both_sides_and_pair_no_child_process(self):
        with tempfile.TemporaryDirectory() as d, patch.object(subprocess, 'Popen', side_effect=AssertionError('no child')):
            result, f = self.exercise(Path(d))
            self.assertEqual(result['state'], 'FIELD_COPY_PAIR_CHECKED_PENDING_PARENT_REVIEW')
            self.assertEqual(result['cross_binary_word_comparisons'], 4608)
            self.assertFalse(result['performance_acceptance'])
            self.assertFalse(result['eda_launched'])

    def test_missing_failed_drifted_or_unchecked_side_reject(self):
        def change_state(f):
            path = f.base/'candidate/result.json'
            result = s.read_json(path); result['state'] = 'PREFLIGHT_NOT_RUN'; s.atomic_json(path, result)
        def active(f):
            path = f.base/'candidate/status.json'
            status = s.read_json(path); status['child_pid'] = 7; s.atomic_json(path, status)
        def drift(f): (f.base/'candidate/work/run.vcs.log').write_text('drift')
        def raw_result(f):
            path = f.base/'candidate/result.json'
            result = s.read_json(path); result['raw_replay']['trials'][0]['cycles'] += 1; s.atomic_json(path, result)
        for mutation in (change_state, active, drift, raw_result):
            with self.subTest(mutation=mutation.__name__), tempfile.TemporaryDirectory() as d, self.assertRaises(Exception):
                self.exercise(Path(d), mutation)


if __name__ == '__main__':
    unittest.main()
